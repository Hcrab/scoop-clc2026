"""The planner's dashboard reads issued, complete product facts without writes."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from test_api_state import api
from scoop.models import (DailyExpectation, Decision, ModelRun, NodeInventory,
                          Plan, Product, ProductTag, Store, StoreOrder, WatchItem)


def widget(title, kind='sku', key='IC001', metric='demand'):
    return {'title': title, 'scope': {'kind': kind, 'key': key},
            'metric': metric, 'threshold': None}


def test_cohort_scope_uses_skus_across_all_stores_and_missing_facts_are_unknown(api):
    client, scope, _, _ = api
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.summary = {'cohort_cards': [{'id': 'cohort-1', 'name': 'Fruit cohort',
                                          'skus': ['IC001'], 'districts': ['Kowloon']}]}
        session.add(Store(id='ST2', name='Second store', district='Island', format='standard',
                          lat=22, lon=114, size_factor=1))
        session.add(StoreOrder(date=date(2026, 7, 5), store_id='ST', sku='IC001',
                               ordered_units=14, shipped_units=10))
        session.add(StoreOrder(date=date(2026, 7, 5), store_id='ST2', sku='IC001',
                               ordered_units=6, shipped_units=4))
        session.add(NodeInventory(date=date(2026, 7, 5), sku='IC001', on_hand_units=21))
    cohort = client.post('/api/plans/TESTAPI/dashboard-preview', json=widget('Network fruit', 'cohort', 'cohort-1')).json()
    assert cohort['value'] == 20
    assert cohort['skus'] == ['IC001']
    assert cohort['recent_demand'][-1] == {'date': '2026-07-05', 'value': 20}
    assert cohort['recent_demand'][-2]['value'] is None
    assert client.post('/api/plans/TESTAPI/dashboard-preview', json=widget('Missing cover', 'cohort', 'cohort-1', 'days_cover')).json()['value'] is None
    with scope() as session:
        session.delete(session.get(StoreOrder, (date(2026, 7, 5), 'ST2', 'IC001')))
    missing = client.post('/api/plans/TESTAPI/dashboard-preview', json=widget('Network fruit', 'cohort', 'cohort-1')).json()
    assert missing['value'] is None and missing['state'] == 'unknown'


def test_expected_uses_issued_run_and_leaves_missing_selected_sku_null(api):
    client, scope, _, _ = api
    with scope() as session:
        session.add(StoreOrder(date=date(2026, 7, 5), store_id='ST', sku='IC001',
                               ordered_units=14, shipped_units=10))
        session.add(ModelRun(id='ISSUED', trained_through=date(2026, 6, 29),
                             created_at=datetime(2026, 6, 30), params={}, metrics={}))
        session.add(DailyExpectation(run_id='ISSUED', date=date(2026, 7, 5),
                                     store_id='ST', sku='IC001', p10=4, p50=8, p90=12))
    value = client.post('/api/plans/TESTAPI/dashboard-preview', json=widget('Expected fruit', metric='requested_vs_expected')).json()
    assert value['series'][-1]['value'] == 14
    assert value['series'][-1]['expected'] == 8
    assert value['series'][-1]['expected_run_id'] == 'ISSUED'
    assert value['series'][-2]['expected'] is None
    with scope() as session:
        session.add(Product(sku='IC002', name='Second fruit', brand='Fixture', format='stick',
                            size_ml=100, units_per_case=10, cases_per_pallet=10, price_hkd=20,
                            cost_hkd=10, supplier_id='SUP', moq_cases=3,
                            launch_date=date(2023, 1, 1), status='active', description='Fixture'))
        session.flush()
        session.add(ProductTag(sku='IC002', tag_id='family:fruit', value_num=1,
                               source='human', confidence=1))
    family = client.post('/api/plans/TESTAPI/dashboard-preview', json=widget('Family', 'tag', 'family:fruit', 'requested_vs_expected')).json()
    assert family['value'] is None
    assert family['series'][-1]['expected'] is None


def test_layout_and_widgets_survive_reads_and_recompute_with_compact_history(api):
    client, scope, _, _ = api
    with scope() as session:
        session.add(WatchItem(id='LEGACY', plan_id='TESTAPI', kind='fill_rate',
                              title='Old watch', assumption='', scope={}, origin='baseline', status='active'))
    added = client.post('/api/plans/TESTAPI/dashboard', json=widget('Fruit demand')).json()
    wid = added['widgets'][0]['id']
    assert added['before']['widgets'] == []
    assert added['after']['widgets'][0]['id'] == wid
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        original_order = list(plan.summary['dashboard_order'])
        original_legacy = session.get(WatchItem, 'LEGACY').status
    assert client.get('/api/plans/TESTAPI').status_code == 200
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'][0]['id'] == wid
    with scope() as session:
        assert session.get(Plan, 'TESTAPI').summary['dashboard_order'] == original_order
        assert session.get(WatchItem, 'LEGACY').status == original_legacy
    changed = client.put('/api/plans/TESTAPI/goal', json={'goal': 'sales'}).json()
    assert changed['edit_id']
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'][0]['id'] == wid
    assert client.post(f"/api/plans/TESTAPI/edits/{changed['edit_id']}/undo").status_code == 200
    plan = client.get('/api/plans/TESTAPI').json()
    assert plan['dashboard']['widgets'][0]['id'] == wid
    history = next(row for row in plan['decisions'] if row['key'] == 'dashboard_add')['value']
    assert history['after']['widgets'][0]['id'] == wid
    assert 'orders' not in history['after'] and 'overrides' not in history['after']
    with scope() as session:
        stored = session.scalar(select(Decision).where(Decision.key == 'dashboard_add'))
        assert stored.value['after']['orders'] and stored.value['after']['watches']


def test_invalid_widget_and_layout_leave_state_unchanged(api):
    client, scope, _, _ = api
    added = client.post('/api/plans/TESTAPI/dashboard', json=widget('One')).json()
    wid = added['widgets'][0]['id']
    before = client.get('/api/plans/TESTAPI/dashboard').json()
    assert client.post('/api/plans/TESTAPI/dashboard', json=widget('Bad', 'sku', 'INVALID')).status_code == 422
    assert client.put(f'/api/plans/TESTAPI/dashboard/{wid}', json=widget('Bad', 'sku', 'INVALID')).status_code == 422
    assert client.put('/api/plans/TESTAPI/dashboard-layout', json={'ids': [wid, wid]}).status_code == 422
    assert client.get('/api/plans/TESTAPI/dashboard').json() == before
    with scope() as session:
        assert len(list(session.scalars(select(Decision).where(Decision.key.like('dashboard_%'))))) == 1


def test_default_widgets_are_seeded_once_by_creation_and_never_restored_by_read(api):
    from scoop import dashboard
    client,scope,_,_=api
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        plan.summary={'cohort_cards':[{'id':'fruit','name':'Fruit cohort','skus':['IC001'],
                                     'effect_pct':12,'interval_pct':[8,16],'case_change':3,'pallet_change':.3}]}
        dashboard.seed_defaults(session,plan)
    first=client.get('/api/plans/TESTAPI/dashboard').json()
    assert len(first['widgets'])==4
    assert first['widgets'][0]['scope']=={'kind':'cohort','key':'fruit'}
    removed=first['widgets'][0]['id']
    assert client.delete('/api/plans/TESTAPI/dashboard/'+removed).status_code==200
    with scope() as session:dashboard.seed_defaults(session,session.get(Plan,'TESTAPI'))
    second=client.get('/api/plans/TESTAPI').json()['dashboard']
    assert removed not in [w['id'] for w in second['widgets']]
    assert len(second['widgets'])==3
