"""Disposable PostgreSQL worlds; no live simulation switch or real model build."""
from datetime import date,datetime
from types import SimpleNamespace
from threading import Thread,Event
import time
import json
from uuid import uuid4
import pandas as pd
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scoop.models import Base,Plan,ChatMessage,StoreOrder,Setting,PurchaseSuggestion,WatchItem,Question,Decision,PurchaseOrder
from scoop.config import settings
from scoop.demo_worlds import WorldManager,SOURCE_FIELDS,WorldPreparationError
from scoop.demo_reset import capture_initial_plan
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
                p=Plan(id='P'+week.strftime('%Y%m%d'),week_start=week,stage='discover',goal='margin',created_at=datetime.now(),summary={'weekly_review':{'status':'complete','report':'Initial evidence'},'discussion_items':[{'id':'initial','status':'open'}]});s.add(p)
                s.add(PurchaseSuggestion(plan_id=p.id,sku='IC001',order_date=week,protection_days=7,demand_p10=10,demand_p50=20,demand_p90=30,adjustment=1,critical_ratio=.5,target_units=40,on_hand_units=10,on_order_units=0,inventory_position=10,suggested_cases=3,capacity_cut_cases=0,final_cases=None,status='suggested',reason='Initial order'))
                s.add(WatchItem(id=p.id+'-W',plan_id=p.id,kind='days_cover',title='Initial widget',assumption='Check cover',scope={},origin='baseline',status='active'))
                s.add(Question(id=p.id+'-Q',plan_id=p.id,stage='discover',finding_id=None,text='Initial topic',options=[],answer=None))
            return p.id
    manager=WorldManager(engine,schema,schema,gate,tiny_world,build,lambda:invalidations.append(1))
    with engine.begin() as c:
        manager.generate(c,42);manager.put(c,'today','2026-07-13')
    build(date(2026,7,13))
    capture_initial_plan(engine,schema,seed=42,week_start=date(2026,7,13),complete=True)
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
        assert s.get(Plan,'P20260713').summary['weekly_review']['report']=='Initial evidence'
        assert s.get(PurchaseSuggestion,('P20260713','IC001')).suggested_cases==3
        assert s.get(WatchItem,'P20260713-W').title=='Initial widget'
        assert s.get(Question,'P20260713-Q').answer is None
        assert s.scalar(select(StoreOrder.ordered_units))==42
        assert s.get(Setting,'provider_budget_marker').value=='retain'
    c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'})
    with Session(engine) as s: assert s.get(Plan,'P20260803').stage=='execute'


def test_public_demo_default_and_reset_removes_context_but_keeps_budget(world):
    from scoop.demo_config import DEMO_SEED, DEMO_WEEK, DEMO_SCENARIO, QUIET_WEEK
    from scoop.demo_worlds import SCENARIOS
    manager,engine,c,_,_=world
    demo=next(s for s in SCENARIOS if s['seed']==DEMO_SEED)
    assert demo['id']==DEMO_SCENARIO and demo['default_week']==DEMO_WEEK
    assert QUIET_WEEK in demo['weeks']
    with engine.begin() as connection:
        manager.put(connection,'cohort_overrides','[{"type":"one_off"}]')
    response=c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'})
    assert response.status_code==200
    with Session(engine) as session:
        assert session.get(Setting,'cohort_overrides') is None
        assert session.get(Setting,'provider_budget_marker').value=='retain'

def test_repeated_fast_reset_restores_initial_state_without_rebuilding(world,monkeypatch):
    manager,engine,c,_,_=world
    with Session(engine) as s,s.begin():
        p=s.get(Plan,'P20260713')
        p.summary={'weekly_review':{'status':'edited','report':'User report'},'discussion_items':[]}
        order=s.get(PurchaseSuggestion,('P20260713','IC001'))
        order.final_cases=99;order.status='confirmed'
        s.get(WatchItem,'P20260713-W').title='Edited widget'
        s.get(Question,'P20260713-Q').answer='yes'
        s.add(Decision(plan_id=p.id,stage='direction',key='manual',value={'ok':True},source='ui',created_at=datetime.now()))
        s.add(PurchaseOrder(id='USER-PO',sku='IC001',supplier_id='SUP',order_date=date(2026,7,13),expected_date=date(2026,7,16),cases=2,source='scoop'))
    def forbidden(*args,**kwargs): raise AssertionError('Fast reset must not rebuild or snapshot')
    monkeypatch.setattr(manager,'snapshot',forbidden)
    monkeypatch.setattr(manager,'build',forbidden)
    monkeypatch.setattr(manager,'invalidate',forbidden)
    monkeypatch.setattr(manager,'generate',forbidden)
    for _ in range(2):
        assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==200
        with Session(engine) as s:
            p=s.get(Plan,'P20260713')
            assert p.stage=='discover'
            assert p.summary['weekly_review']['report']=='Initial evidence'
            assert p.summary['discussion_items'][0]['status']=='open'
            assert s.get(PurchaseSuggestion,('P20260713','IC001')).final_cases is None
            assert s.get(WatchItem,'P20260713-W').title=='Initial widget'
            assert s.get(Question,'P20260713-Q').answer is None
            assert s.scalar(select(Decision)) is None
            assert s.scalar(select(ChatMessage)) is None
            assert s.scalar(select(PurchaseOrder).where(PurchaseOrder.source=='scoop')) is None
            assert s.scalar(select(StoreOrder.ordered_units))==42
            assert s.get(Setting,'provider_budget_marker').value=='retain'
    reopened=WorldManager(engine,manager.active,manager.namespace,manager.gate,tiny_world,forbidden,forbidden)
    reopened.snapshot=forbidden
    assert reopened.choose('july-context','2026-07-13',reset=True)['id']=='P20260713'

def test_fast_reset_rolls_back_if_restore_fails(world,monkeypatch):
    from scoop import demo_reset
    manager,engine,c,_,_=world
    original=demo_reset.restore_initial_plan
    def broken(connection,schema,rows):
        original(connection,schema,rows)
        raise RuntimeError('injected restore failure')
    monkeypatch.setattr(demo_reset,'restore_initial_plan',broken)
    response=c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'})
    assert response.status_code==503
    with Session(engine) as s:
        assert s.get(Plan,'P20260713').stage=='direction'
        assert s.scalar(select(ChatMessage.content))=='Preserve this progress'
        assert s.scalar(select(StoreOrder.ordered_units))==42

def test_fast_reset_does_not_wait_for_background_read_only_requests(world):
    manager,_,c,_,_=world
    started=Event();release=Event()
    @c.app.get('/slow-read')
    def slow_read():
        with manager.gate.activity():
            started.set();release.wait(3)
            return {'read':True}
    reader=Thread(target=lambda:c.get('/slow-read'));reader.start()
    assert started.wait(1)
    try:
        start=time.monotonic()
        response=c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'})
        assert response.status_code==200
        assert time.monotonic()-start<1
        assert not release.is_set()
    finally:
        release.set();reader.join(3)

def test_fast_reset_waits_for_a_real_mutation_then_clears_it(world):
    manager,engine,c,_,_=world
    started=Event();release=Event();reset_done=Event()
    @c.app.post('/slow-write')
    def slow_write():
        started.set();release.wait(3)
        with Session(engine) as session,session.begin():
            session.add(ChatMessage(plan_id='P20260713',stage='discover',role='user',content='Finishing write',meta={},created_at=datetime.now()))
        return {'saved':True}
    writer=Thread(target=lambda:c.post('/slow-write'));writer.start();assert started.wait(1)
    def reset():
        assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==200
        reset_done.set()
    resetter=Thread(target=reset);resetter.start()
    try:
        time.sleep(.1);assert not reset_done.is_set()
        release.set();writer.join(3);resetter.join(3)
        assert reset_done.is_set()
        with Session(engine) as session:assert session.scalar(select(ChatMessage)) is None
    finally:
        release.set();writer.join(3);resetter.join(3)

def test_first_authored_report_is_saved_from_the_active_transaction(world):
    from scoop.demo_reset import template_key
    manager,engine,c,_,_=world
    week=date(2026,7,13);key=template_key(42,week)
    with Session(engine) as s,s.begin():
        s.query(ChatMessage).delete()
        p=s.get(Plan,'P20260713');p.stage='discover'
        setting=s.get(Setting,key);initial=json.loads(setting.value)
        initial['complete']=False;setting.value=json.dumps(initial)
        p.summary={**p.summary,'weekly_review':{'status':'complete','report':'First authored report'},
                   'flow':{'step':'orders','max_step':'orders'}}
        s.flush()
        assert capture_initial_plan(week_start=week,complete=True,connection=s.connection())
    assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':week.isoformat()}).status_code==200
    with Session(engine) as s:
        p=s.get(Plan,'P20260713')
        assert p.summary['weekly_review']['report']=='First authored report'
        assert p.summary['flow']=={'step':'report','max_step':'report','notice':None}

def test_manual_order_change_cannot_become_the_initial_report_template(world):
    from scoop.demo_reset import template_key
    _,engine,_,_,_=world
    week=date(2026,7,13)
    with Session(engine) as s,s.begin():
        s.query(ChatMessage).delete()
        p=s.get(Plan,'P20260713');p.stage='discover'
        setting=s.get(Setting,template_key(42,week));initial=json.loads(setting.value)
        initial['complete']=False;setting.value=json.dumps(initial)
        s.get(PurchaseSuggestion,('P20260713','IC001')).final_cases=9
        s.flush()
        assert not capture_initial_plan(week_start=week,complete=True,connection=s.connection())

def test_reset_of_a_new_week_prepares_once_without_world_copy_or_ai(world,monkeypatch):
    manager,engine,c,_,_=world
    built=[];original=manager.build
    def build(week,*,report=True):
        assert report is False
        built.append(week)
        return original(week,report=report)
    def forbidden(*args,**kwargs):raise AssertionError('Source and models stay unchanged')
    monkeypatch.setattr(manager,'build',build)
    monkeypatch.setattr(manager,'snapshot',forbidden)
    monkeypatch.setattr(manager,'invalidate',forbidden)
    body={'scenario_id':'july-context','week_start':'2026-07-20'}
    for _ in range(2):
        assert c.post('/api/demo-settings/reset',json=body).status_code==200
    assert built==[date(2026,7,20)]
    with Session(engine) as s:
        assert s.get(Plan,'P20260713') is None
        assert s.get(Plan,'P20260720').stage=='discover'
        assert s.scalar(select(ChatMessage)) is None

def test_same_world_new_week_builds_once_without_snapshot_or_invalidation(world,monkeypatch):
    manager,engine,c,_,_=world
    built=[]
    original=manager.builder
    def count_build(week):
        built.append(week)
        return original(week)
    manager.builder=count_build
    def forbidden(*args,**kwargs): raise AssertionError('No world source change')
    monkeypatch.setattr(manager,'snapshot',forbidden)
    monkeypatch.setattr(manager,'invalidate',forbidden)
    body={'scenario_id':'july-context','week_start':'2026-07-20'}
    assert c.post('/api/demo-settings/select',json=body).status_code==200
    with Session(engine) as s:
        assert s.get(Plan,'P20260720').summary['weekly_review']['report']=='Initial evidence'
        s.get(Plan,'P20260720').stage='execute'
        s.commit()
    assert c.post('/api/demo-settings/select',json=body).status_code==200
    assert built==[date(2026,7,20)]
    with Session(engine) as s:
        assert s.get(Plan,'P20260720').stage=='execute'
        assert s.get(Plan,'P20260713').stage=='direction'

def test_failures_restore_previous_world_transactionally(world):
    manager,engine,c,fail,invalidations=world
    for body in [{'scenario_id':'missing','week_start':'2026-07-13'},{'scenario_id':'july-context','week_start':'2026-07-14'}]: assert c.post('/api/demo-settings/select',json=body).status_code==422
    fail.append(True)
    assert c.post('/api/demo-settings/select',json={'scenario_id':'august-seed73','week_start':'2026-08-03'}).status_code==503
    assert manager.active_seed()==42
    with Session(engine) as s:
        assert s.get(Plan,'P20260713').stage=='direction'
        assert s.scalar(select(StoreOrder.ordered_units))==42
    assert c.post('/api/demo-settings/reset',json={'scenario_id':'july-context','week_start':'2026-07-13'}).status_code==200
    with Session(engine) as s: assert s.scalar(select(ChatMessage.content)) is None
    assert len(invalidations)==2

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
