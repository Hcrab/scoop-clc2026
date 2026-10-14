"""Exploration math, operational cutoffs and previews without training/network."""
from datetime import date, timedelta
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from test_api_state import api
from scoop.ai import exploration_tools as tools
from scoop.algorithms import cusum
from scoop.algorithms.groups import Group
from scoop.models import DirectionItem, Plan, Product, Promotion, PurchaseOrder, Store, StoreOrder


@pytest.fixture
def exploration(api,monkeypatch):
    _,scope,_,_=api
    catalog=[Group('family:fruit','Fruit','family',('IC001','B','C','D')),
             Group('band:price_hkd:1','Mid price','price_hkd',('IC001','B','D')),
             Group('format:cone','Cones','format',('IC001','B','C')),
             Group('format:only_d','Only D','format',('D',))]
    monkeypatch.setattr(tools,'_groups',lambda session:{g.id:g for g in catalog})
    expected=[]
    with scope() as session:
        product=session.get(Product,'IC001')
        values={column.name:getattr(product,column.name) for column in Product.__table__.columns}
        for sku in ('B','C','D'):session.add(Product(**{**values,'sku':sku,'name':'Product '+sku}))
        session.add(Store(id='ST2',name='Island store',district='HK Island',format='standard',lat=22,lon=114,size_factor=1))
        session.flush()
        for day in pd.date_range('2026-05-04','2026-07-13'):
            for store_id in ('ST','ST2'):
                for sku,units in [('IC001',10),('B',20),('C',30),('D',40)]:
                    actual=units+(10 if sku=='IC001' else 5 if sku=='B' else 0) if day>=pd.Timestamp('2026-07-06') and store_id=='ST' else units
                    if day==pd.Timestamp('2026-07-13'):actual=1_000_000_000
                    row=session.get(StoreOrder,(day.date(),store_id,sku))
                    if row:row.ordered_units=actual;row.shipped_units=actual-2
                    else:session.add(StoreOrder(date=day.date(),store_id=store_id,sku=sku,ordered_units=actual,shipped_units=actual-2))
                    expected.append({'date':day,'store_id':store_id,'sku':sku,'mean':units if day<pd.Timestamp('2026-07-13') else 1_000_000_000,
                                     'model_version':'M202607-fixture' if day.month==7 else 'M202606-fixture'})
        session.add_all([
            Promotion(id='PROMO',sku='IC001',start_date=date(2026,7,10),end_date=date(2026,7,20),discount_pct=.2,note='Operational promotion'),
            Promotion(id='FUTURE',sku='IC001',start_date=date(2026,7,13),end_date=date(2026,7,20),discount_pct=.9,note='Future'),
            PurchaseOrder(id='RECEIVED',sku='IC001',supplier_id='SUP',order_date=date(2026,7,1),expected_date=date(2026,7,7),received_date=date(2026,7,9),cases=3,source='history'),
            PurchaseOrder(id='PENDING',sku='B',supplier_id='SUP',order_date=date(2026,7,10),expected_date=date(2026,7,14),received_date=date(2026,7,18),cases=4,source='history'),
            PurchaseOrder(id='LATER_ISSUE',sku='IC001',supplier_id='SUP',order_date=date(2026,7,13),expected_date=date(2026,7,20),received_date=None,cases=99,source='history'),
        ])
        session.get(Plan,'TESTAPI').week_start=date(2026,7,13)
    frame=pd.DataFrame(expected)
    monkeypatch.setattr(tools,'_expectations',lambda session:frame.copy())
    return scope,frame


def run(scope,name,args):
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        before={'summary':dict(plan.summary),'goal':plan.goal,'stage':plan.stage}
        result=tools.execute(name,args,session,plan)
        assert before=={'summary':dict(plan.summary),'goal':plan.goal,'stage':plan.stage}
        assert not session.dirty and not session.new and not session.deleted
        json.dumps(result,allow_nan=False)
        return result


def test_catalog_and_strict_parameter_contract(exploration):
    scope,_=exploration
    result=run(scope,'catalog_groups',{})
    assert result['districts']==['HK Island','Kowloon']
    assert len(result['groups'])==4
    mid=next(g for g in result['groups'] if g['id']=='band:price_hkd:1')
    assert mid['sku_count']==3 and mid['skus']==['IC001','B','D']
    assert {d['name'] for d in tools.declarations()}=={'catalog_groups','query_group','query_operations','preview_group_orders'}
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        for name,args in [('query_group',{'group_ids':[]}),('query_group',{'group_ids':['format:cone'],'window_days':29}),
                          ('query_operations',{'group_ids':['format:cone'],'sql':'SELECT anything'}),
                          ('preview_group_orders',{'group_ids':['format:cone'],'factor':2})]:
            with pytest.raises(ValidationError):tools.execute(name,args,session,plan)
        with pytest.raises(ValueError,match='group IDs'):tools.execute('query_group',{'group_ids':['hidden:event']},session,plan)
        with pytest.raises(ValueError,match='districts'):tools.execute('query_group',{'group_ids':['format:cone'],'districts':['Unknown']},session,plan)


def test_prior_year_curve_uses_same_products_and_district_without_filling_missing_days(exploration):
    scope,_=exploration
    with scope() as session:
        for store,sku,units in [('ST','IC001',19),('ST','B',41),('ST','C',999),('ST2','IC001',1000)]:
            session.add(StoreOrder(date=date(2025,7,6),store_id=store,sku=sku,ordered_units=units,shipped_units=units))
    result=run(scope,'query_group',{'group_ids':['band:price_hkd:1','format:cone'],'districts':['Kowloon'],'window_days':7})
    assert result['daily'][0]['prior_year_requested_units']==60
    assert result['daily'][1]['prior_year_requested_units'] is None


def test_intersection_cutoff_share_and_decomposition(exploration,monkeypatch):
    scope,_=exploration
    dates=[]
    calibrate=cusum.calibrate
    monkeypatch.setattr(cusum,'calibrate',lambda frame:(dates.append(frame.date.max()) or calibrate(frame)))
    args={'group_ids':['band:price_hkd:1','format:cone'],'districts':['Kowloon'],'window_days':7}
    result=run(scope,'query_group',args)
    assert result['scope']['skus']==['B','IC001']
    assert result['evidence_through']=='2026-07-12'
    assert result['recent']['requested_units']==315
    assert result['recent']['expected_units']==210
    assert result['recent']['actual_share']==pytest.approx(45/115)
    assert result['recent']['expected_share']==pytest.approx(.3)
    assert result['before']['requested_units']==210
    decomposition=result['shift_share']
    assert decomposition['change']==pytest.approx(105)
    assert sum(decomposition[k] for k in ('volume','mix','interaction'))==pytest.approx(105)
    assert max(dates)<pd.Timestamp(result['window_start'])
    assert len(result['daily'])==7 and result['daily'][-1]['date']=='2026-07-12'
    assert result['cusum']['status']=='computed'
    assert result['cusum']['family_fdr_significant'] is False
    assert result['sample']['adequate'] is False
    assert [r['sku'] for r in result['sku_contributors']]==['IC001','B']
    assert len(result['parents'])==2
    result=run(scope,'query_group',{**args,'denominator_group_id':'band:price_hkd:1'})
    assert result['recent']['actual_share']==pytest.approx(45/85)
    with scope() as session:
        with pytest.raises(ValueError,match='encompass'):
            tools.execute('query_group',{**args,'denominator_group_id':'format:only_d'},session,session.get(Plan,'TESTAPI'))


def test_empty_intersection_and_no_change_are_honest(exploration):
    scope,_=exploration
    result=run(scope,'query_group',{'group_ids':['format:cone','format:only_d'],'window_days':7})
    assert result['scope']['sku_count']==0 and result['recent']['requested_units']==0
    assert result['sku_contributors']==[] and result['sample']['adequate'] is False
    assert result['cusum']['status']=='empty_group'
    result=run(scope,'query_group',{'group_ids':['format:cone'],'districts':['HK Island'],'window_days':7})
    assert result['recent']['excess_units']==0
    assert result['shift_share']['change']==0
    assert result['sample']['adequate'] is True
    assert all(c['up']==0 and c['down']==0 and not c['crossed'] for c in result['cusum']['checks'])


def test_operations_hide_future_receipts_and_future_issued_orders(exploration):
    scope,_=exploration
    result=run(scope,'query_operations',{'group_ids':['band:price_hkd:1','format:cone'],'districts':['Kowloon'],'window_days':7})
    assert result['fulfillment']['requested_units']==315
    assert result['fulfillment']['shipped_units']==287
    assert result['fulfillment']['fill_rate']==pytest.approx(287/315)
    assert result['promotions']['overlap_count']==1
    assert result['promotions']['items'][0]['end_date']=='2026-07-12'
    assert result['observed_receipts']['late_count']==1
    assert result['observed_receipts']['mean_delay_days']==2
    arrival=result['known_open_arrivals']['items'][0]
    assert result['known_open_arrivals']['count']==1 and arrival['sku']=='B'
    assert arrival['expected_date']=='2026-07-14' and 'received_date' not in arrival
    assert '2026-07-18' not in json.dumps(result)


def test_preview_uses_order_algorithm_and_replaces_overlapping_district_factors(exploration,monkeypatch):
    from scoop import planning
    from scoop.algorithms.replenish import SkuInput, plan_orders
    scope,_=exploration
    with scope() as session:
        old=session.get(DirectionItem,'TESTAPI-D');old.bucket='more';old.factor=1.2;old.districts=['Kowloon','HK Island']
        session.add(DirectionItem(id='OVERLAP',plan_id='TESTAPI',tag_id='band:price_hkd:1',bucket='more',factor=1.1,districts=['Kowloon'],note='Test'))
    catalog=tools._groups(None)
    monkeypatch.setattr(tools,'_preview_ready',lambda plan:None)
    monkeypatch.setattr(planning,'monitoring',lambda:SimpleNamespace(group_by_id=catalog,store_district={'ST':'Kowloon','ST2':'HK Island'}))
    calls=[]
    split=pd.DataFrame([{'sku':sku,'store_id':store,'mean':50.} for sku in ('IC001','B','C','D') for store in ('ST','ST2')])
    monkeypatch.setattr(tools,'_forecast_split',lambda plan:split.copy())
    def suggest(day,directions,**kwargs):
        calls.append(directions)
        adjustment=planning.sku_adjustments(directions,split)
        items=[SkuInput(sku=sku,mean=100*adjustment[sku],pdays=10,price=20,cost=10,
                        units_per_case=10,cases_per_pallet=10,moq_cases=3,on_hand=0,on_order=0,lead_days=3,adjustment=adjustment[sku]) for sku in adjustment.index]
        return plan_orders(items,np.array([1.]),capacity_pallets=100)
    monkeypatch.setattr(planning,'suggest_orders',suggest)
    result=run(scope,'preview_group_orders',{'group_ids':['band:price_hkd:1','format:cone'],'districts':['Kowloon'],'factor':1.5})
    adjusted=planning.sku_adjustments(calls[1],split)
    assert adjusted['IC001']==pytest.approx(.5*1.2+.5*1.5)
    assert adjusted['B']==pytest.approx(.5*1.2+.5*1.5)
    assert adjusted['C']==pytest.approx(1.2)
    assert adjusted['D']==pytest.approx(1.2*1.05)
    assert len([d for d in calls[1] if d['sku']=='IC001' and 'Kowloon' in d['districts']])==1
    assert result['preview']['cases']>result['baseline']['cases']
    assert result['preview']['capacity_pallets']==10
    assert result['preview']['above_physical_capacity_pallets']==pytest.approx(max(0,result['preview']['projected_peak_pallets']-10))
    assert result['applied'] is False
    with scope() as session:
        assert session.get(DirectionItem,'TESTAPI-D').factor==1.2
        assert session.get(DirectionItem,'OVERLAP').factor==1.1
    result=run(scope,'preview_group_orders',{'group_ids':['format:cone','format:only_d'],'factor':1.5})
    assert result['delta_cases']==0 and result['products']==[]


def test_missing_expected_history_has_no_invented_detector(exploration,monkeypatch):
    scope,frame=exploration
    monkeypatch.setattr(tools,'_expectations',lambda session:frame[frame.date>=pd.Timestamp('2026-07-10')].copy())
    result=run(scope,'query_group',{'group_ids':['format:cone'],'window_days':7})
    assert result['sample']['adequate'] is False
    assert result['cusum']['status']=='insufficient_history'
    assert result['daily'][0]['expected_share'] is None
    assert result['daily'][0]['expected_units'] is None
    assert result['daily'][0]['excess_units'] is None


def test_unprepared_preview_never_starts_training(monkeypatch):
    monkeypatch.setattr(tools.runs,'_ARTIFACTS',None)
    monkeypatch.setattr(tools.runs,'build_artifacts',lambda:pytest.fail('Read-only previews must not train models'))
    with pytest.raises(ValueError,match='Prepared monthly purchasing artifacts'):
        tools._preview_ready(SimpleNamespace(week_start=date(2026,7,13)))
