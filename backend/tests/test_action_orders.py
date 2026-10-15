"""Grouped review and atomic approval of the actual case list."""
from sqlalchemy import select, func
from test_api_state import api
from scoop.models import Plan, PurchaseSuggestion, Decision


def test_order_groups_use_cohort_first_and_list_each_sku_once(api,monkeypatch):
    client, scope, _, planning = api
    seen=[]
    original=planning.confirmation_capacity
    def capacity(day,cases,factors):
        seen.append(factors)
        return original(day,cases,factors)
    monkeypatch.setattr(planning,'confirmation_capacity',capacity)
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        plan.summary={'cohort_cards':[{'id':'first','name':'Leading cohort','skus':['IC001']},
                                      {'id':'overlap','name':'Overlapping cohort','skus':['IC001']}]}
        session.get(PurchaseSuggestion,('TESTAPI','IC001')).adjustment=1.35
    result=client.get('/api/plans/TESTAPI/order-summary')
    assert result.status_code==200,result.text
    assert result.json()['groups']==[{'id':'first','name':'Leading cohort','skus':['IC001']}]
    assert result.json()['edited_skus']==[]
    assert result.json()['capacity']['projected_peak_pallets']>0
    assert seen==[{'IC001':1.35}]


def test_approve_orders_is_atomic_and_idempotent(api,monkeypatch):
    client, scope, _, planning = api
    with scope() as session:
        session.get(Plan,'TESTAPI').stage='direction'
        session.get(PurchaseSuggestion,('TESTAPI','IC001')).final_cases=2
    rejected=client.post('/api/plans/TESTAPI/approve-orders')
    assert rejected.status_code==422,rejected.text
    with scope() as session:
        assert session.get(Plan,'TESTAPI').stage=='direction'
        assert session.get(PurchaseSuggestion,('TESTAPI','IC001')).status=='suggested'
        session.get(PurchaseSuggestion,('TESTAPI','IC001')).final_cases=5
    result=client.post('/api/plans/TESTAPI/approve-orders')
    assert result.status_code==200,result.text
    assert result.json()['stage']=='execute'
    assert client.post('/api/plans/TESTAPI/approve-orders').status_code==200
    with scope() as session:
        assert session.get(PurchaseSuggestion,('TESTAPI','IC001')).final_cases==5
        assert session.get(PurchaseSuggestion,('TESTAPI','IC001')).status=='confirmed'
        assert session.scalar(select(func.count()).select_from(Decision).where(Decision.key=='orders_approved'))==1


def test_approve_overcapacity_does_not_partially_confirm(api,monkeypatch):
    client, scope, _, planning=api
    with scope() as session:session.get(Plan,'TESTAPI').stage='direction'
    monkeypatch.setattr(planning,'confirmation_capacity',lambda *args:{'feasible':False,'incremental_overcapacity_pallets':2})
    assert client.post('/api/plans/TESTAPI/approve-orders').status_code==409
    with scope() as session:
        assert session.get(Plan,'TESTAPI').stage=='direction'
        assert session.get(PurchaseSuggestion,('TESTAPI','IC001')).status=='suggested'


def test_zero_cases_can_be_approved_and_case_edit_marker_is_exact(api):
    client, scope, _, _ = api
    with scope() as session:
        session.get(Plan, 'TESTAPI').stage = 'direction'
    edited = client.post('/api/plans/TESTAPI/orders/bulk', json={
        'filter': {'skus': ['IC001']}, 'change': {'type': 'set_cases', 'value': 0}})
    assert edited.status_code == 200, edited.text
    summary = client.get('/api/plans/TESTAPI/order-summary').json()
    assert summary['edited_skus'] == ['IC001']
    assert client.post('/api/plans/TESTAPI/approve-orders').status_code == 200
    with scope() as session:
        order = session.get(PurchaseSuggestion, ('TESTAPI', 'IC001'))
        assert order.final_cases == 0 and order.status == 'confirmed'
        assert session.get(Plan, 'TESTAPI').summary['approved_capacity']['feasible']
