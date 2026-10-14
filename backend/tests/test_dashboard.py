"""Dashboard persistence and historical math use the disposable API schema."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from test_api_state import api
from scoop.models import Plan, StoreOrder, NodeInventory, WatchItem, Decision
from scoop.ai import tools


def spec(metric='demand', key='IC001', threshold=None):
    return {'title': f'{metric} for fruit', 'scope': {'kind': 'sku', 'key': key},
            'metric': metric, 'threshold': threshold}


def history(scope):
    with scope() as session:
        # Seven prior days support the 5 July cover calculation.
        for i in range(7):
            day = date(2026, 7, 5) - timedelta(days=i + 1)
            session.add(StoreOrder(date=day, store_id='ST', sku='IC001', ordered_units=7, shipped_units=5))
        session.add(StoreOrder(date=date(2026, 7, 5), store_id='ST', sku='IC001', ordered_units=14, shipped_units=10))
        session.add(NodeInventory(date=date(2026, 7, 5), sku='IC001', on_hand_units=21))


def test_dashboard_math_preview_threshold_and_missing(api):
    client, scope, _, _ = api
    history(scope)
    samples = {'demand': 14, 'lost_units': 4, 'fill_rate': 10 / 14,
               'on_hand': 21, 'pallets': .21, 'days_cover': 3}
    for metric, expected in samples.items():
        response = client.post('/api/plans/TESTAPI/dashboard-preview', json=spec(metric))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['value'] == expected
        assert data['series'][0]['value'] is None
        assert data['state'] == 'normal'
        assert len(data['series']) == 28
    warning = client.post('/api/plans/TESTAPI/dashboard-preview', json=spec('fill_rate', threshold={'operator': 'lt', 'value': .8})).json()
    assert warning['state'] == 'warning'
    assert client.post('/api/plans/TESTAPI/dashboard-preview', json=spec(key='OTHER')).status_code == 422
    assert client.get('/api/plans/MISSING/dashboard').status_code == 404


def test_widget_order_edits_undo_and_plan_isolation(api):
    client, scope, _, _ = api
    initial = client.get('/api/plans/TESTAPI/dashboard').json()
    assert len(initial['widgets']) == 3
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] == initial['widgets']
    added = client.post('/api/plans/TESTAPI/dashboard', json=spec()).json()
    assert added['edit_id'] and added['affected_orders'] == []
    wid = added['widgets'][-1]['id']
    ids = [wid, *[w['id'] for w in initial['widgets']]]
    layout = client.put('/api/plans/TESTAPI/dashboard-layout', json={'ids': ids}).json()
    assert [w['id'] for w in layout['widgets']] == ids
    assert client.put('/api/plans/TESTAPI/dashboard-layout', json={'ids': [wid, wid]}).status_code == 422
    assert client.put('/api/plans/TESTAPI/dashboard/unknown', json=spec()).status_code == 404
    with scope() as session:
        session.add(Plan(id='OTHERPLAN', week_start=date(2026, 6, 29), stage='discover', goal='margin', created_at=datetime.now(), summary={'dashboard_order': []}))
    assert client.put(f'/api/plans/OTHERPLAN/dashboard/{wid}', json=spec()).status_code == 404
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        current = tools.context(session, plan)
        assert [w['id'] for w in current['dashboard']['widgets']] == ids
        assert 'watches' not in current
        # An unrelated order change after a widget edit must not block its undo.
        plan.goal = 'sales'
        session.flush()
        undone = tools.execute('undo_edit', {'edit_id': layout['edit_id']}, session, plan, 'discover')[0]
        assert undone['undone']
        assert plan.goal == 'sales'
    assert [w['id'] for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets']] == ids[1:]+ids[:1]
    removed = client.delete(f'/api/plans/TESTAPI/dashboard/{wid}').json()
    assert wid not in [w['id'] for w in removed['widgets']]
    restored = client.post(f"/api/plans/TESTAPI/edits/{removed['edit_id']}/undo").json()
    assert restored['undone']
    assert wid in [w['id'] for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets']]
    revised = {**spec('lost_units'), 'title': 'Fruit shortfall'}
    changed = client.put(f'/api/plans/TESTAPI/dashboard/{wid}', json=revised).json()
    assert next(w for w in changed['widgets'] if w['id'] == wid)['metric'] == 'lost_units'
    assert client.post(f"/api/plans/TESTAPI/edits/{changed['edit_id']}/undo").json()['undone']
    assert next(w for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] if w['id'] == wid)['metric'] == 'demand'


def test_intentionally_empty_dashboard_stays_empty(api):
    client, _, _, _ = api
    ids = [w['id'] for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets']]
    for wid in ids:
        assert client.delete(f'/api/plans/TESTAPI/dashboard/{wid}').status_code == 200
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] == []


def test_chat_widget_add_remove_with_receipts(api):
    client, scope, _, _ = api
    added = client.post('/api/plans/TESTAPI/chat', json={'message': 'Watch Fixture Fruit demand', 'stage': 'discover'}).json()
    assert added['actions'][0]['type'] == 'edit', added
    wid = next(w['id'] for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] if w['title'].startswith('Dashboard:'))
    removed = client.post('/api/plans/TESTAPI/chat', json={'message': 'Remove watch Fixture Fruit', 'stage': 'discover'}).json()
    assert removed['actions'][0]['type'] == 'edit', removed
    assert wid not in [w['id'] for w in client.get('/api/plans/TESTAPI/dashboard').json()['widgets']]
