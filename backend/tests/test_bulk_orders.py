"""Bulk order edits persist case overrides and share exact undo."""
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select, func

from test_api_state import api
from scoop.ai import chat, tools
from scoop.algorithms.groups import Group
from scoop.algorithms.replenish import SkuInput, plan_orders
from scoop.api.cohorts import order_snapshot
from scoop.cohort_context import load_overrides
from scoop.models import Decision, Plan, Product, ProductTag, PurchaseSuggestion, Tag


def prepare(api, monkeypatch):
    client, scope, _, planning = api
    from scoop.ai import exploration_tools
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {
        'family:fruit': Group('family:fruit', 'Fruit', 'family', ('IC001','IC002')),
        'band:price_100ml:0': Group('band:price_100ml:0', 'Lower price / 100 ml', 'price_100ml', ('IC001',))})
    with scope() as session:
        session.add(Product(sku='IC002',name='Fixture Chocolate',brand='Other',format='stick',size_ml=100,
            units_per_case=10,cases_per_pallet=10,price_hkd=20,cost_hkd=10,supplier_id='SUP',moq_cases=1,
            launch_date=date(2023,1,1),status='active',description='Fixture'))
        session.flush()
        session.add(ProductTag(sku='IC002',tag_id='family:fruit',value_num=1,source='human',confidence=1))
        session.add(PurchaseSuggestion(plan_id='TESTAPI',sku='IC002',order_date=date(2026,7,6),protection_days=10,
            demand_p10=20,demand_p50=30,demand_p90=40,adjustment=1,critical_ratio=.8,target_units=40,
            on_hand_units=10,on_order_units=0,inventory_position=10,suggested_cases=4,capacity_cut_cases=0,
            status='suggested',reason='Fixture'))
        plan=session.get(Plan,'TESTAPI')
        plan.summary={'cohort_model':{'leaves':[{'id':'FRUIT','tag_path':[{'id':'family:fruit','included':True}],
            'districts':['Kowloon'],'skus':['IC001','IC002']}],
            'units':[{'sku':'IC001','district':'Kowloon'},{'sku':'IC002','district':'Kowloon'}]}}

    def fake_orders(as_of,directions,**kwargs):
        overrides=kwargs.get('overrides') or []
        edits={x['value']['sku']:x['value']['cases'] for x in overrides if x['type']=='cases'}
        limited=kwargs.get('capacity_limit')
        cases={'IC001':3,'IC002':4}
        if limited is not None:
            cases={'IC001':1,'IC002':1}  # separate greedy test checks the real algorithm
        rows=[]
        for sku in ('IC001','IC002'):
            amount=edits.get(sku,cases[sku]) if kwargs.get('apply_case_overrides',True) else cases[sku]
            rows.append({'sku':sku,'order_date':as_of,'pdays':10,'demand_p10':20.,'demand_p50':30.,
                'demand_p90':40.,'adjustment':1.,'critical_ratio':.8,'target_units':40.,
                'on_hand_units':10,'on_order_units':0,'inventory_position':10,
                'suggested_cases':cases[sku],'capacity_cut_cases':0,'final_cases':amount})
        frame=pd.DataFrame(rows)
        frame.attrs['cohort_model']={'leaves':[],'sku_factors':{},'cases_overrides':edits}
        return frame
    monkeypatch.setattr(planning,'suggest_orders',fake_orders)
    return client,scope


def test_filter_percent_persistence_and_exact_undo(api,monkeypatch):
    client,scope=prepare(api,monkeypatch)
    body={'filter':{'group':'band:price_100ml:0','family':'family:fruit','brand':'Fixture','district':'Kowloon',
                    'skus':['IC001','IC002']},'change':{'type':'percent','value':50}}
    before=client.get('/api/plans/TESTAPI').json()['orders']
    response=client.post('/api/plans/TESTAPI/orders/bulk',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['affected_orders']==[{'sku':'IC001','before':3,'after':5,'factor_before':1.,'factor_after':1.}]
    assert result['capacity']['projected_peak_pallets']>0
    with scope() as session:
        assert load_overrides(session)[0]['value']=={'sku':'IC001','cases':5}
        assert session.get(PurchaseSuggestion,('TESTAPI','IC001')).final_cases==5
        assert session.get(PurchaseSuggestion,('TESTAPI','IC002')).final_cases is None
        # Opening the cards refreshes derived evidence after the edit receipt.
        plan=session.get(Plan,'TESTAPI')
        plan.summary={**plan.summary,'cohort_cards':[{'id':'refreshed'}],
                      'cohort_model':{'leaves':[]},'discussion':{'messages':['kept']}}
    undo=client.post(f"/api/plans/TESTAPI/edits/{result['edit_id']}/undo")
    assert undo.status_code==200,undo.text
    with scope() as session:
        assert load_overrides(session)==[]
        assert order_snapshot(session,session.get(Plan,'TESTAPI'))[0]['suggested_cases']==3
        assert session.get(Plan,'TESTAPI').summary['discussion']=={'messages':['kept']}


def test_set_cases_and_invalid_filter_are_atomic(api,monkeypatch):
    client,scope=prepare(api,monkeypatch)
    bad=client.post('/api/plans/TESTAPI/orders/bulk',json={'filter':{'skus':['IC001','BAD']},
        'change':{'type':'set_cases','value':2}})
    assert bad.status_code==422
    with scope() as session:
        assert load_overrides(session)==[]
        assert session.scalar(select(func.count()).select_from(Decision))==0
    good=client.post('/api/plans/TESTAPI/orders/bulk',json={'filter':{'skus':['IC001']},
        'change':{'type':'set_cases','value':0}})
    assert good.status_code==200,good.text
    assert good.json()['affected_orders'][0]['after']==0


def test_scripted_percent_and_missing_amount(api,monkeypatch):
    client,scope=prepare(api,monkeypatch)
    missing=client.post('/api/plans/TESTAPI/chat',json={'message':'Order more Fixture Fruit','stage':'discover'}).json()
    assert missing['actions']==[]
    changed=client.post('/api/plans/TESTAPI/chat',json={'message':'Order 50% more Fixture Fruit','stage':'discover'}).json()
    assert changed['actions'][0]['type']=='edit',changed
    assert changed['actions'][0]['affected_orders'][0]['after']==5


def test_model_cannot_supply_missing_order_quantity():
    from scoop.ai.gemini import _quantity_authorized
    assert not _quantity_authorized('Order more Fruit',{'change':{'type':'percent','value':10}})
    assert _quantity_authorized('Order 10% more Fruit',{'change':{'type':'percent','value':10}})
    assert not _quantity_authorized('Fit capacity at 90%',{'change':{'type':'fit_capacity','value':.8}})
    assert _quantity_authorized('Set IC001 to 5 cases',{'change':{'type':'set_cases','value':5}})


def test_fit_capacity_persists_whole_plan_and_reports_unavoidable_excess(api,monkeypatch):
    client,scope=prepare(api,monkeypatch)
    from scoop import planning
    original=planning.suggest_orders
    calls=[]
    def track(*args,**kwargs):
        if kwargs.get('capacity_limit') is not None:
            calls.append(kwargs['capacity_limit'])
            assert kwargs['initial_cases']=={'IC001':3,'IC002':4}
        return original(*args,**kwargs)
    monkeypatch.setattr(planning,'suggest_orders',track)
    monkeypatch.setattr(planning,'confirmation_capacity',lambda day,cases:{
        'capacity_pallets':10.,'projected_peak_pallets':10.2,'inherited_peak_pallets':10.2,
        'incremental_overcapacity_pallets':0.,'feasible':True})
    result=client.post('/api/plans/TESTAPI/orders/bulk',json={
        'filter':{},'change':{'type':'fit_capacity','value':.9}})
    assert result.status_code==200,result.text
    edit=result.json()
    assert calls==[9.]
    assert edit['capacity']['target_pallets']==9.
    assert edit['capacity']['inherited_excess_pallets']>1
    assert edit['capacity']['target_met'] is False
    with scope() as session:
        assert {x['value']['sku'] for x in load_overrides(session)}=={'IC001','IC002'}
    assert client.post(f"/api/plans/TESTAPI/edits/{edit['edit_id']}/undo").status_code==200


def test_fit_capacity_uses_existing_greedy_and_reports_inherited_excess():
    items=[SkuInput(sku='A',mean=100,pdays=7,price=20,cost=10,units_per_case=10,cases_per_pallet=10,
        moq_cases=1,on_hand=20,on_order=0,lead_days=2,adjustment=1),
        SkuInput(sku='B',mean=100,pdays=7,price=20,cost=10,units_per_case=10,cases_per_pallet=10,
        moq_cases=1,on_hand=20,on_order=0,lead_days=2,adjustment=1)]
    ratios=np.array([.8,1,1.2])
    baseline=np.array([[100.,100.],[100.,100.]])
    mask=np.array([[False,False],[True,True]])
    tight=plan_orders(items,ratios,.9,capacity_baseline=baseline,arrival_mask=mask)
    loose=plan_orders(items,ratios,3.,capacity_baseline=baseline,arrival_mask=mask)
    assert tight.final_cases.sum()<loose.final_cases.sum()
    assert tight.inherited_overcapacity_pallets.iloc[0]>0
    assert tight.projected_pallets.iloc[0]>=tight.inherited_overcapacity_pallets.iloc[0]+.9


def test_capacity_fit_starts_from_current_cases_instead_of_new_recommendation():
    item=SkuInput(sku='A',mean=10,pdays=7,price=20,cost=10,units_per_case=10,
        cases_per_pallet=10,moq_cases=1,on_hand=20,on_order=0,lead_days=2)
    ratios=np.array([.8,1,1.2])
    assert plan_orders([item],ratios,2).final_cases.iloc[0]==0
    retained=plan_orders([item],ratios,2,initial_cases={'A':9})
    assert retained.final_cases.iloc[0]==9
    reduced=plan_orders([item],ratios,.7,initial_cases={'A':9})
    assert reduced.final_cases.iloc[0]==5
    assert reduced.capacity_cut_cases.iloc[0]==4
    assert reduced.projected_pallets.iloc[0]<=.7+1e-10
