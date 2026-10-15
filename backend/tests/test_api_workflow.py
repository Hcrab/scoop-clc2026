"""Dashboard and order approval regressions in disposable API schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from sqlalchemy import event, func, select

from test_api_state import api
from scoop.models import Decision, NodeInventory, Plan, PurchaseSuggestion, WatchItem


def spec(title, metric='on_hand', threshold=None):
    return {'title': title, 'scope': {'kind': 'sku', 'key': 'IC001'},
            'metric': metric, 'threshold': threshold}


def widgets(client, pid='TESTAPI'):
    return client.get(f'/api/plans/{pid}/dashboard').json()['widgets']


def test_order_approval_is_atomic_idempotent_and_widgets_remain_editable(api):
    c, scope, _, _ = api
    with scope() as s:
        s.get(Plan, 'TESTAPI').stage = 'direction'
        s.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).final_cases = 2
    assert c.post('/api/plans/TESTAPI/approve-orders').status_code == 422
    with scope() as s:
        assert s.get(Plan, 'TESTAPI').stage == 'direction'
        assert s.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).status == 'suggested'
        s.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).final_cases = 3
    assert c.post('/api/plans/TESTAPI/approve-orders').json()['stage'] == 'execute'
    assert c.post('/api/plans/TESTAPI/approve-orders').json()['stage'] == 'execute'
    with scope() as s:
        assert s.scalar(select(func.count()).select_from(Decision).where(Decision.key == 'orders_approved')) == 1
        assert s.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).status == 'confirmed'
    added = c.post('/api/plans/TESTAPI/dashboard', json=spec('Execution stock'))
    assert added.status_code == 200, added.text
    assert any(w['title'] == 'Execution stock' for w in widgets(c))
    assert c.put('/api/plans/TESTAPI/directions/TESTAPI-D', json={
        'bucket': 'more', 'factor': 1.2, 'districts': ['Kowloon']}).status_code == 409


def test_full_widget_update_archive_persistence_and_exact_undo(api):
    c, scope, _, _ = api
    created = c.post('/api/plans/TESTAPI/dashboard', json=spec('Original'))
    assert created.status_code == 200, created.text
    wid = next(w['id'] for w in created.json()['widgets'] if w['title'] == 'Original')
    original = c.get('/api/plans/TESTAPI/dashboard').json()
    edited_spec = spec('Revised', 'on_hand', {'operator': 'lt', 'value': 3})
    updated = c.put(f'/api/plans/TESTAPI/dashboard/{wid}', json=edited_spec)
    assert updated.status_code == 200, updated.text
    assert updated.json()['before']['widgets'][0]['title'] == 'Original'
    assert updated.json()['after']['widgets'][0]['title'] == 'Revised'
    assert c.put(f'/api/plans/TESTAPI/dashboard/{wid}', json={
        **edited_spec, 'scope': {'kind': 'sku', 'key': 'MISSING'}}).status_code == 422
    assert c.put(f'/api/plans/TESTAPI/dashboard/{wid}', json={
        **edited_spec, 'title': None}).status_code == 422
    assert widgets(c)[0]['title'] == 'Revised'
    archived = c.delete(f'/api/plans/TESTAPI/dashboard/{wid}')
    assert archived.status_code == 200, archived.text
    assert wid not in {w['id'] for w in widgets(c)}
    assert wid not in {w['id'] for w in c.get('/api/plans/TESTAPI').json()['dashboard']['widgets']}
    with scope() as s:
        assert s.get(WatchItem, wid).status == 'archived'
    assert c.post(f"/api/plans/TESTAPI/edits/{archived.json()['edit_id']}/undo").status_code == 200
    assert widgets(c)[0]['title'] == 'Revised'
    assert c.post(f"/api/plans/TESTAPI/edits/{updated.json()['edit_id']}/undo").status_code == 200
    assert c.get('/api/plans/TESTAPI/dashboard').json() == original


def test_layout_uses_exact_active_ids_and_undo_restores_orders(api):
    c, scope, _, _ = api
    for title in ('First', 'Second'):
        response = c.post('/api/plans/TESTAPI/dashboard', json=spec(title))
        assert response.status_code == 200, response.text
    before = c.get('/api/plans/TESTAPI').json()
    ids = [w['id'] for w in before['dashboard']['widgets']]
    changed = c.put('/api/plans/TESTAPI/dashboard-layout', json={'ids': ids[::-1]})
    assert changed.status_code == 200, changed.text
    assert [w['id'] for w in widgets(c)] == ids[::-1]
    assert c.put('/api/plans/TESTAPI/dashboard-layout', json={'ids': [ids[0], ids[0]]}).status_code == 422
    assert [w['id'] for w in widgets(c)] == ids[::-1]
    assert c.get('/api/plans/TESTAPI').json()['orders'] == before['orders']
    assert c.post(f"/api/plans/TESTAPI/edits/{changed.json()['edit_id']}/undo").status_code == 200
    restored = c.get('/api/plans/TESTAPI').json()
    assert restored['dashboard'] == before['dashboard']
    assert restored['orders'] == before['orders']


def test_separate_plans_have_separate_widgets_and_reads_do_not_rebuild(api):
    c, scope, _, _ = api
    created = c.post('/api/plans/TESTAPI/dashboard', json=spec('Previous choice'))
    assert created.status_code == 200, created.text
    previous_id = next(w['id'] for w in created.json()['widgets'] if w['title'] == 'Previous choice')
    with scope() as s:
        s.add(Plan(id='NEXTAPI', week_start=date(2026, 7, 13), stage='discover',
                   goal='margin', created_at=datetime.now(), summary={}))
    first = c.get('/api/plans/NEXTAPI').json()
    second = c.get('/api/plans/NEXTAPI').json()
    assert first['dashboard'] == second['dashboard']
    assert first['dashboard']['widgets'] == []
    assert previous_id in {w['id'] for w in widgets(c)}
    with scope() as s:
        assert s.get(Plan, 'NEXTAPI').summary == {}
        assert s.scalar(select(func.count()).select_from(WatchItem).where(WatchItem.plan_id == 'NEXTAPI')) == 0
    assert c.post('/api/plans/NEXTAPI/dashboard', json=spec('New choice')).status_code == 200
    assert {w['title'] for w in widgets(c, 'NEXTAPI')} == {'New choice'}
    assert {w['title'] for w in widgets(c)} == {'Previous choice'}


def test_missing_values_thresholds_and_read_freshness(api):
    c, scope, _, _ = api
    threshold = {'operator': 'lt', 'value': 3}
    created = c.post('/api/plans/TESTAPI/dashboard', json=spec('Stock', threshold=threshold))
    assert created.status_code == 200, created.text
    wid = created.json()['widgets'][0]['id']
    initial = widgets(c)[0]
    assert initial['value'] is None and initial['state'] == 'unknown'
    assert initial['series'][-1] == {'date': '2026-07-05', 'value': None}
    assert all(point['date'] < '2026-07-06' for point in initial['series'])
    with scope() as s:
        s.add(NodeInventory(date=date(2026, 7, 5), sku='IC001', on_hand_units=1))
    assert widgets(c)[0]['value'] == 1 and widgets(c)[0]['state'] == 'warning'
    with scope() as s:
        s.get(NodeInventory, (date(2026, 7, 5), 'IC001')).on_hand_units = 10
    assert widgets(c)[0]['value'] == 10 and widgets(c)[0]['state'] == 'normal'
    assert c.get('/api/plans/TESTAPI/dashboard').json()['facts_through'] == '2026-07-05'
    assert c.get('/api/plans/TESTAPI/dashboard').json()['widgets'][0]['id'] == wid


def test_concurrent_duplicate_creation_leaves_one_widget(api):
    c, scope, _, _ = api
    body = spec('Concurrent choice')
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: c.post('/api/plans/TESTAPI/dashboard', json=body), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 422], [r.text for r in responses]
    assert sum(w['title'] == body['title'] for w in widgets(c)) == 1
    with scope() as s:
        assert s.scalar(select(func.count()).select_from(WatchItem).where(
            WatchItem.plan_id == 'TESTAPI', WatchItem.title == body['title'])) == 1


def test_batched_history_reads_and_closed_plan_protection(api):
    c, scope, _, _ = api
    from scoop import dashboard
    with scope() as s:
        plan = s.get(Plan, 'TESTAPI')
        for i in range(20):
            dashboard.save(s, plan, spec(f'Batch {i}'))
        engine = s.get_bind()
        statements = []
        def executed(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(engine, 'before_cursor_execute', executed)
        try:
            result = dashboard.view(s, plan)
        finally:
            event.remove(engine, 'before_cursor_execute', executed)
        assert len(result['widgets']) == 20
        assert sum('from store_orders' in sql for sql in statements) == 1
        assert sum('from node_inventory' in sql for sql in statements) == 1
        plan.stage = 'closed'
    assert c.get('/api/plans/TESTAPI/dashboard').status_code == 200
    assert c.post('/api/plans/TESTAPI/dashboard', json=spec('Cannot add')).status_code == 409
    assert c.put('/api/plans/TESTAPI/dashboard/' + result['widgets'][0]['id'],
                 json=spec('Cannot edit')).status_code == 409
    assert c.delete('/api/plans/TESTAPI/dashboard/' + result['widgets'][0]['id']).status_code == 409
    assert c.put('/api/plans/TESTAPI/dashboard-layout', json={
        'ids': [w['id'] for w in result['widgets']]}).status_code == 409
