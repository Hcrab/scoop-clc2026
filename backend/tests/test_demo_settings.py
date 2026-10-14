"""Disposable PostgreSQL worlds; no live simulation switch or real model build."""
from datetime import date,datetime
from types import SimpleNamespace
from threading import Thread,Event
import time
from uuid import uuid4
import pandas as pd
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scoop.models import Base,Plan,ChatMessage,StoreOrder,Setting
from scoop.config import settings
from scoop.demo_worlds import WorldManager,SOURCE_FIELDS,WorldPreparationError
from scoop.demo_gate import ActivityGate,DemoBusy,DemoGateMiddleware
from scoop.api import demo_settings

def tiny_world(seed):
    frames={field:pd.DataFrame() for field in SOURCE_FIELDS.values()}
    frames.update(
        stores=pd.DataFrame([dict(id='ST',name=f'Seed{seed} store',district='Kowloon',format='standard',lat=22.,lon=114.,size_factor=1.)]),
        nodes=pd.DataFrame([dict(id='DC1',name='Test cold store',kind='dc_cold_store',capacity_pallets=62)]),
        suppliers=pd.DataFrame([dict(id='SUP',name='Test supplier',lead_time_days=3,lead_time_sd=0.,order_weekday=0,review_days=7)]),
        products=pd.DataFrame([dict(sku='IC001',name=f'Seed{seed} product',brand='Test',format='stick',size_ml=100,units_per_case=10,cases_per_pallet=10,price_hkd=20.,cost_hkd=10.,supplier_id='SUP',moq_cases=3,launch_date=date(2023,1,1),status='active',description='Test product')]),
        store_orders=pd.DataFrame([dict(date=date(2026,6,1),store_id='ST',sku='IC001',ordered_units=seed,shipped_units=seed)]),
        node_inventory=pd.DataFrame([dict(date=date(2026,6,1),sku='IC001',on_hand_units=seed+100)]))
    return SimpleNamespace(**frames)

@pytest.fixture
def world(monkeypatch,request):
    schema='test_demo_'+uuid4().hex
    admin=create_engine(settings.database_url)
    with admin.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(settings.database_url,connect_args={'options':f'-csearch_path={schema}'})
    Base.metadata.create_all(engine)
    fail=[];invalidations=[];gate=ActivityGate()
    def build(week):
        if fail: raise RuntimeError('test plan failure')
        with Session(engine) as s,s.begin():
            p=s.scalar(select(Plan).where(Plan.week_start==week))
            if not p:
                p=Plan(id='P'+week.strftime('%Y%m%d'),week_start=week,stage='discover',goal='margin',created_at=datetime.now(),summary={});s.add(p)
            return p.id
    manager=WorldManager(engine,schema,schema,gate,tiny_world,build,lambda:invalidations.append(1))
    with engine.begin() as c:
        manager.generate(c,42);manager.put(c,'today','2026-07-13')
    build(date(2026,7,13))
    with Session(engine) as s,s.begin():
        s.get(Plan,'P20260713').stage='direction'
        s.add(ChatMessage(plan_id='P20260713',stage='discover',role='user',content='Preserve this progress',meta={},created_at=datetime.now()))
        s.add(Setting(key='provider_budget_marker',value='retain'))
    def cleanup():
        engine.dispose()
        with admin.begin() as c:
            for name in [schema,manager.schema(42),manager.schema(73),schema+'_reset_backup']: c.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        admin.dispose()
    request.addfinalizer(cleanup)
    monkeypatch.setattr(demo_settings,'manager',manager)
    app=FastAPI();app.include_router(demo_settings.router);app.add_middleware(DemoGateMiddleware,manager=manager,activity_gate=gate)
    @app.get('/api/evaluation')
    def evaluation(): return {'seed42_score':999}
    @app.get('/api/bootstrap')
    def bootstrap(): return {'evaluation':{'seed42_score':999},'metadata':{},'products':[]}
    with TestClient(app) as client: yield manager,engine,client,fail,invalidations

def test_real_distinct_seed_data_and_roundtrip_progress(world):
    manager,engine,c,_,invalidations=world
    assert c.get('/api/demo-settings').json()['scenario_id']=='july-context'
    body={'scenario_id':'august-seed73','week_start':'2026-08-03'}
    assert c.post('/api/demo-settings/select',json=body).json()['id']=='P20260803'
    with Session(engine) as s:
        assert s.scalar(select(StoreOrder.ordered_units))==73
        assert s.get(Plan,'P20260713') is None
    assert c.post('/api/demo-settings/select',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==200
    with Session(engine) as s:
        assert s.scalar(select(StoreOrder.ordered_units))==42
        assert s.get(Plan,'P20260713').stage=='direction'
        assert s.scalar(select(ChatMessage.content))=='Preserve this progress'
    reopened=WorldManager(engine,manager.active,manager.namespace,manager.gate,tiny_world,manager.builder,manager.invalidate)
    assert reopened.info()['scenario_id']=='july-context'
    assert len(invalidations)==2

def test_reset_scope_and_other_world_survives(world):
    manager,engine,c,_,_=world
    c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'})
    with Session(engine) as s,s.begin(): s.get(Plan,'P20260803').stage='execute'
    c.post('/api/demo-settings/select',json={'scenario_id':'july-context','week_start':'2026-07-13'})
    assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==200
    with Session(engine) as s:
        assert s.get(Plan,'P20260713').stage=='discover'
        assert list(s.scalars(select(ChatMessage)))==[]
        assert s.scalar(select(StoreOrder.ordered_units))==42
        assert s.get(Setting,'provider_budget_marker').value=='retain'
    c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'})
    with Session(engine) as s: assert s.get(Plan,'P20260803').stage=='execute'

def test_failures_restore_previous_world_transactionally(world):
    manager,engine,c,fail,invalidations=world
    for body in [{'scenario_id':'missing','week_start':'2026-07-13'},{'scenario_id':'july-context','week_start':'2026-07-14'}]: assert c.post('/api/demo-settings/select',json=body).status_code==422
    fail.append(True)
    assert c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'}).status_code==503
    assert manager.active_seed()==42
    with Session(engine) as s:
        assert s.get(Plan,'P20260713').stage=='direction'
        assert s.scalar(select(StoreOrder.ordered_units))==42
    assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==503
    with Session(engine) as s: assert s.scalar(select(ChatMessage.content))=='Preserve this progress'
    assert len(invalidations)==4

def test_gate_tracks_worker_after_response_disconnect():
    gate=ActivityGate();started=Event();release=Event();switched=Event()
    def worker():
        with gate.activity(): started.set();release.wait(2)
    def replace():
        with gate.replacement(timeout=2): switched.set()
    with gate.activity(http=True):
        thread=Thread(target=worker);thread.start();assert started.wait(1)
    writer=Thread(target=replace);writer.start();time.sleep(.05)
    assert not switched.is_set()
    with pytest.raises(DemoBusy):
        with gate.activity(http=True): pass
    release.set();thread.join(2);writer.join(2);assert switched.is_set()

def test_gate_existing_nested_work_avoids_waiting_writer_deadlock():
    gate=ActivityGate();done=Event()
    with gate.activity(http=True):
        def replace():
            with gate.replacement(timeout=2): done.set()
        writer=Thread(target=replace);writer.start();time.sleep(.03)
        with gate.activity(): pass
        assert not done.is_set()
    writer.join(2);assert done.is_set()

def test_evaluation_is_not_relabelled_for_another_seed(world):
    _,_,c,_,_=world
    assert c.get('/api/evaluation').json()['seed42_score']==999
    c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'})
    assert c.get('/api/evaluation').json()=={'status':'pending','seed':73}
    data=c.get('/api/bootstrap').json()
    assert data['evaluation'] is None
    assert 'seed42' in data['metadata']['evaluation_provenance']

def test_all_loaded_runtime_caches_are_invalidated(monkeypatch):
    import sys
    from scoop.demo_worlds import clear_runtime_caches
    called=[]
    for name in ['scoop.algorithms.runs','scoop.monitoring']:
        monkeypatch.setitem(sys.modules,name,SimpleNamespace(reset_cache=lambda name=name:called.append(name)))
    capacity_cache={'old-world':123}
    monkeypatch.setitem(sys.modules,'scoop.planning',SimpleNamespace(_CAPACITY_DEMAND_CACHE=capacity_cache))
    protection_cache={'old-world':456};daily_cache={'old-world':789}
    monkeypatch.setitem(sys.modules,'scoop.algorithms.forecast',SimpleNamespace(_PROTECTION_CACHE=protection_cache,_DAILY_MEAN_CACHE=daily_cache))
    clear_runtime_caches()
    assert called==['scoop.algorithms.runs','scoop.monitoring']
    assert capacity_cache=={}
    assert protection_cache=={} and daily_cache=={}
