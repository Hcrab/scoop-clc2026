"""API integration uses disposable PostgreSQL schemas, never resets demo facts."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from uuid import uuid4
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session
from scoop.config import settings
from scoop.main import app
from scoop.api import service
from scoop.models import *

@pytest.fixture
def api(monkeypatch, request):
    schema='test_api_'+uuid4().hex
    admin=create_engine(settings.database_url)
    with admin.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(settings.database_url,connect_args={'options':f'-csearch_path={schema}'})
    def cleanup():
        engine.dispose()
        with admin.begin() as c: c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
    request.addfinalizer(cleanup)
    Base.metadata.create_all(engine)
    @contextmanager
    def scope():
        with Session(engine) as s:
            try: yield s; s.commit()
            except Exception: s.rollback(); raise
    clock={'today':'2026-07-13'}
    monkeypatch.setattr(service,'session_scope',scope)
    monkeypatch.setattr(service,'cached_series',lambda *args:[])
    monkeypatch.setattr(service,'get_setting',lambda key,default=None:clock.get(key,default))
    monkeypatch.setattr(service,'set_setting',lambda key,value:clock.update({key:value}))
    with scope() as s:
        s.add(Supplier(id='SUP',name='Fixture supplier',lead_time_days=3,lead_time_sd=0,order_weekday=0,review_days=7))
        s.add(Store(id='ST',name='Fixture store',district='Kowloon',format='standard',lat=22,lon=114,size_factor=1))
        s.add(Node(id='DC1',name='Fixture DC',kind='dc_cold_store',capacity_pallets=10))
        s.add(TagDimension(id='family',name='Family',kind='single',definition='Fixture',source='human'))
        s.flush()
        s.add(Product(sku='IC001',name='Fixture Fruit',brand='Fixture',format='stick',size_ml=100,units_per_case=10,cases_per_pallet=10,price_hkd=20,cost_hkd=10,supplier_id='SUP',moq_cases=3,launch_date=date(2023,1,1),status='active',description='Fixture'))
        s.add(Tag(id='family:fruit',dimension_id='family',name='Fruit',definition='Fixture'))
        s.add(Plan(id='TESTAPI',week_start=date(2026,7,6),stage='discover',goal='margin',created_at=datetime.now(),summary={}))
        s.flush()
        s.add(ProductTag(sku='IC001',tag_id='family:fruit',value_num=1,source='human',confidence=1))
        s.add(Finding(id='TESTAPI-F',plan_id='TESTAPI',kind='significant',tag_id='family:fruit',district='Kowloon',direction='up',statistic=5,threshold=4,p_value=.01,q_value=.02,share_before=.2,share_now=.3,effect_volume=1,effect_mix=2,effect_interaction=0,source='scan',classification='unsure',explanation='Fixture observed rise',evidence={'districts':['Kowloon'],'display':'Fruit family'}))
        s.flush()
        s.add(Question(id='TESTAPI-Q',plan_id='TESTAPI',stage='discover',finding_id='TESTAPI-F',text='Persistent?',options={'options':[{'value':'persistent','label':'Persistent'},{'value':'watch','label':'Watch'}],'recommended':'watch'}))
        s.add(DirectionItem(id='TESTAPI-D',plan_id='TESTAPI',bucket='hold',tag_id='family:fruit',districts=['Kowloon'],factor=1,finding_id='TESTAPI-F',note='Fixture'))
        s.add(PurchaseSuggestion(plan_id='TESTAPI',sku='IC001',order_date=date(2026,7,6),protection_days=10,demand_p10=20,demand_p50=30,demand_p90=40,adjustment=1,critical_ratio=.8,target_units=40,on_hand_units=10,on_order_units=0,inventory_position=10,suggested_cases=3,capacity_cut_cases=0,status='suggested',reason='Fixture'))
        for day,units in [(date(2026,7,12),10),(date(2026,7,13),99999)]:
            s.add(StoreOrder(date=day,store_id='ST',sku='IC001',ordered_units=units,shipped_units=units))
            s.add(NodeInventory(date=day,sku='IC001',on_hand_units=10))
    import scoop.planning as planning
    def fake_orders(as_of,directions,service_level=None,goal='margin',**kwargs):
        return pd.DataFrame([{'sku':'IC001','order_date':as_of,'pdays':10,'demand_p10':20.,'demand_p50':30.,'demand_p90':40.,'adjustment':directions[0]['factor'],'critical_ratio':service_level or (.97 if goal=='fill_rate' else .8),'target_units':50. if goal=='fill_rate' else 40.,'on_hand_units':10,'on_order_units':0,'inventory_position':10,'suggested_cases':4 if goal=='fill_rate' else 3,'capacity_cut_cases':0}])
    monkeypatch.setattr(planning,'suggest_orders',fake_orders)
    monkeypatch.setattr(planning,'confirmation_capacity',lambda day,cases:{'capacity_pallets':10,'projected_peak_pallets':.1+sum(cases.values())/10,'inherited_peak_pallets':.1,'incremental_overcapacity_pallets':max(0,.1+sum(cases.values())/10-10),'feasible':.1+sum(cases.values())/10<=10})
    with TestClient(app) as client:
        yield client,scope,clock,planning

def test_discovery_persists_and_locks(api):
    c,scope,_,_=api
    assert c.get('/api/plans/TESTAPI').json()['questions'][0]['options']['options'][0]['id']=='persistent'
    assert c.post('/api/plans/TESTAPI/advance').status_code==409
    assert c.post('/api/plans/TESTAPI/questions/TESTAPI-Q',json={'answer':'persistent'}).status_code==200
    data=c.get('/api/plans/TESTAPI').json()
    assert data['findings'][0]['classification']=='persistent'
    assert data['directions'][0]['bucket']=='more'
    assert data['orders'][0]['adjustment']==pytest.approx(1.5)
    before=len(data['decisions'])
    c.post('/api/plans/TESTAPI/questions/TESTAPI-Q',json={'answer':'persistent'})
    assert len(c.get('/api/plans/TESTAPI').json()['decisions'])==before
    assert c.post('/api/plans/TESTAPI/advance').json()['stage']=='direction'
    assert c.post('/api/plans/TESTAPI/questions/TESTAPI-Q',json={'answer':'one_off'}).status_code==409
    assert c.put('/api/plans/TESTAPI/directions/TESTAPI-D',json={'bucket':'less','factor':1.2,'districts':['Kowloon']}).status_code==422

def test_saved_discovery_uses_its_original_model_curve(api,monkeypatch):
    c,scope,_,_=api
    versions=[]
    monkeypatch.setattr(service,'cached_series',lambda tag,districts,start,cutoff,version=None:versions.append(version) or [])
    assert c.get('/api/plans/TESTAPI').status_code==200
    assert versions and all(version is None for version in versions)
    versions.clear()
    with scope() as s:
        p=s.get(Plan,'TESTAPI');p.summary={**p.summary,'model_run':{'version':'M202607-v1-s42'}}
        f=s.get(Finding,'TESTAPI-F');f.evidence={**f.evidence,'model_version':'M202606-v1-s42'}
    assert c.get('/api/plans/TESTAPI').status_code==200
    assert versions[0]=='M202606-v1-s42'

def test_cached_chart_excludes_future_points(monkeypatch):
    import scoop.monitoring as monitoring
    calls=[]
    curve=pd.DataFrame([{'group':'family:fruit','district':'Kowloon','date':pd.Timestamp(day),'actual_share':.3,'expected_share':.2,'s_up':1.,'s_down':0.} for day in ['2026-07-05','2026-07-06']])
    monkeypatch.setattr(monitoring,'historical_chart',lambda cutoff,version:calls.append((cutoff,version)) or (None,curve))
    result=service.cached_series('family:fruit',['Kowloon'],date(2026,7,1),date(2026,7,6),'saved-version')
    assert calls==[(date(2026,7,6),'saved-version')]
    assert len(result)==1 and result[0]['date'].startswith('2026-07-05')

def test_recompute_failure_rolls_back(api,monkeypatch):
    c,scope,_,planning=api
    assert c.put('/api/plans/TESTAPI/goal',json={'goal':'fill_rate','service_level':.98}).status_code==200
    assert c.get('/api/plans/TESTAPI').json()['orders'][0]['critical_ratio']==.98
    def fail(*args,**kwargs): raise ValueError('fixture failed calculation')
    monkeypatch.setattr(planning,'suggest_orders',fail)
    assert c.put('/api/plans/TESTAPI/goal',json={'goal':'sales','service_level':.99}).status_code==503
    data=c.get('/api/plans/TESTAPI').json()
    assert data['plan']['goal']=='fill_rate'
    assert data['orders'][0]['critical_ratio']==.98
    assert c.put('/api/plans/TESTAPI/goal',json={'goal':'sales','service_level':1}).status_code==422

def test_execute_confirmation_idempotent_and_capacity(api):
    c,scope,_,_=api
    with scope() as s: s.get(Plan,'TESTAPI').stage='execute'
    assert c.put('/api/plans/TESTAPI/goal',json={'goal':'sales'}).status_code==409
    assert c.post('/api/plans/TESTAPI/orders/IC001/confirm',json={'cases':2}).status_code==422
    assert c.post('/api/plans/TESTAPI/orders/IC001/confirm',json={'cases':10000}).status_code==409
    assert c.post('/api/plans/TESTAPI/orders/IC001/confirm',json={'cases':3.1}).status_code==422
    for _ in range(2): assert c.post('/api/plans/TESTAPI/orders/IC001/confirm',json={'cases':3}).status_code==200
    with scope() as s:
        assert s.scalar(select(func.count()).select_from(PurchaseOrder))==1
        assert s.scalar(select(func.count()).select_from(Decision))==1
    assert c.post('/api/plans/TESTAPI/orders/IC001/confirm',json={'cases':4}).status_code==409
    assert 'confirmed' in c.get('/api/plans/TESTAPI/orders.csv').text

def test_cutoff_clock_reuse_and_watch_archive(api,monkeypatch):
    c,scope,clock,planning=api
    data=c.get('/api/bootstrap').json()
    assert data['metrics']['ordered_units']==10
    detail=c.get('/api/stores/ST').json()
    assert all(row['date']<'2026-07-13' for row in detail['daily'])
    monkeypatch.setattr(planning,'build_plan',lambda *args,**kwargs:pytest.fail('Existing plan must not be recreated'))
    assert c.post('/api/plans',json={'week_start':'2026-07-06'}).json()=={'id':'TESTAPI'}
    assert c.post('/api/plans',json={'week_start':'2026-07-20'}).status_code==422
    assert c.put('/api/clock',json={'today':'2026-09-01'}).status_code==422
    body={'kind':'fill_rate','title':'Fixture watch','assumption':'99%','scope':{}}
    wid=c.post('/api/plans/TESTAPI/watch',json=body).json()['id']
    assert c.post('/api/plans/TESTAPI/watch',json=body).json()['id']==wid
    assert next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['id']==wid)['series']==[{'date':'2026-07-12','value':1.0}]
    assert c.delete('/api/plans/TESTAPI/watch/'+wid).status_code==200
    with scope() as s: assert s.get(WatchItem,wid).status=='archived'

def test_chat_persists_actions_and_rejects_completed_stage(api):
    c,scope,_,_=api
    response=c.post('/api/plans/TESTAPI/chat',json={'message':'set goal to fill rate 97%','stage':'discover'})
    assert response.status_code==200
    assert response.json()['actions'][0]['goal']=='fill_rate'
    with scope() as s: s.get(Plan,'TESTAPI').stage='direction'
    response=c.post('/api/plans/TESTAPI/chat',json={'message':'more fruit 20%','stage':'direction'})
    assert response.json()['actions'][0]['factor']==1.2
    assert c.post('/api/plans/TESTAPI/chat',json={'message':'set goal to sales','stage':'discover'}).status_code==409
    assert c.post('/api/plans/TESTAPI/chat',json={'message':'watch fruit','stage':'direction'}).json()['actions'][0]['type']=='watch'
    data=c.get('/api/plans/TESTAPI').json()
    assert len(data['messages'])==6
    assert all(m['meta']['provider']=='scripted' for m in data['messages'])

def test_historical_plan_metrics_and_sku_watch_thresholds(api):
    c,scope,_,_=api
    assert c.get('/api/bootstrap').json()['metrics']['ordered_units']==10
    assert c.get('/api/plans/TESTAPI').json()['metrics']['ordered_units']==0
    with scope() as s:
        s.get(NodeInventory,(date(2026,7,12),'IC001')).on_hand_units=1
        s.add(WatchItem(id='LOW',plan_id='TESTAPI',kind='days_cover',title='Low cover',scope={'mode':'below_lead'},assumption='Lead time',origin='baseline',status='active'))
    watch=next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['id']=='LOW')
    assert (watch['value'],watch['unit'],watch['state'])==(1,'SKUs','warning')
    with scope() as s:
        s.get(NodeInventory,(date(2026,7,12),'IC001')).on_hand_units=1000
        s.get(WatchItem,'LOW').scope={'mode':'excess'}
        for i in range(6): s.add(StoreOrder(date=date(2026,7,6)+timedelta(days=i),store_id='ST',sku='IC001',ordered_units=10,shipped_units=10))
    assert next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['id']=='LOW')['value']==1

def test_refresh_watches_tracks_final_direction_and_keeps_user_items(api,monkeypatch):
    from types import SimpleNamespace
    c,scope,_,planning=api
    monkeypatch.setattr(planning,'monitoring',lambda:SimpleNamespace(group_by_id={'family:fruit':SimpleNamespace(id='family:fruit',name='Fruit')}))
    with scope() as s:
        p=s.get(Plan,'TESTAPI')
        service.refresh_watches(s,p)
        s.add(WatchItem(id='custom',plan_id=p.id,kind='fill_rate',title='My custom watch',scope={},assumption='Keep',origin='user',status='active'))
    with scope() as s:
        s.get(DirectionItem,'TESTAPI-D').bucket='more'
        service.refresh_watches(s,s.get(Plan,'TESTAPI'))
    with scope() as s:
        active=[w.title for w in service.objects(s,WatchItem,'TESTAPI') if w.status=='active']
        assert 'My custom watch' in active
        assert any(w.kind=='tag_share' and 'higher demand share continues' in w.assumption for w in service.objects(s,WatchItem,'TESTAPI') if w.status=='active')
        assert sum(w.kind=='tag_share' for w in service.objects(s,WatchItem,'TESTAPI') if w.status=='active')==1


def test_large_persistent_shift_matches_supported_direction_range(api):
    c,scope,_,_=api
    with scope() as s:
        f=s.get(Finding,'TESTAPI-F');f.share_before=.1;f.share_now=.4
    assert c.post('/api/plans/TESTAPI/questions/TESTAPI-Q',json={'answer':'persistent'}).status_code==200
    detail=c.get('/api/plans/TESTAPI').json()
    assert detail['directions'][0]['factor']==2
    assert c.post('/api/plans/TESTAPI/advance').status_code==200
    assert c.put('/api/plans/TESTAPI/directions/TESTAPI-D',json={'bucket':'more','factor':3,'districts':['Kowloon']}).status_code==422
    assert c.get('/api/plans/TESTAPI').json()['directions'][0]['factor']==2
