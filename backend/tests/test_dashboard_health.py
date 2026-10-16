"""Health tiles are historical facts, independent of the editable dashboard."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from test_api_state import api
from test_dashboard import history, spec
from scoop import dashboard
from scoop.models import Plan, WatchItem


def test_fixed_health_uses_only_recorded_period_with_no_widgets(api):
    client, scope, _, _ = api
    history(scope)
    before = client.get('/api/plans/TESTAPI/dashboard').json()
    assert before['widgets'] == []
    health = before['health']
    assert health['period_start'] == '2026-06-08'
    assert health['through'] == '2026-07-05'
    # The fixture's 12 and 13 July rows must not leak into a 6 July plan.
    assert health['requested_units'] == 63
    assert health['shipped_units'] == 45
    assert health['fill_rate'] == pytest.approx(45 / 63)
    assert health['stockout_skus'] == ['IC001']
    assert health['stockout_sku_days'] == 8
    assert health['pallets'] == .21
    assert health['peak_pallets'] == .21
    assert health['capacity_pallets'] == 10
    product = health['products'][0]
    assert product['recent_demand'] == [7] * 6 + [14]
    assert product['daily_demand'] == 8
    assert product['days_cover'] == 21 / 8
    assert product['lead_time_days'] == 3
    assert client.get('/api/plans/TESTAPI/dashboard').json() == before
    with scope() as session:
        assert list(session.scalars(select(WatchItem))) == []
        assert session.get(Plan, 'TESTAPI').summary == {}


def test_stock_widget_evidence_and_ranked_cover_metric(api):
    client, scope, _, _ = api
    history(scope)
    stock = client.post('/api/plans/TESTAPI/dashboard-preview', json=spec('on_hand')).json()
    latest = stock['series'][-1]
    assert latest['value'] == 21
    assert latest['requested_units'] == 14
    assert latest['days_cover'] == 3
    assert latest['safe_stock_units'] == 21
    lowest = client.post('/api/plans/TESTAPI/dashboard-preview', json=spec('lowest_cover'))
    assert lowest.status_code == 200, lowest.text
    assert lowest.json()['value'] == 3
    assert lowest.json()['unit'] == 'days'


def default_specs():
    return [
        {'title': 'Fruit stock', 'scope': {'kind': 'sku', 'key': 'IC001'}, 'metric': 'on_hand'},
        {'title': 'Cold-store use', 'scope': {'kind': 'warehouse'}, 'metric': 'pallets'},
        {'title': 'Lowest cover', 'scope': {'kind': 'warehouse'}, 'metric': 'lowest_cover'},
    ]


def test_analyst_defaults_replace_only_untouched_seed_layout(api):
    client, scope, _, _ = api
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        dashboard.seed_defaults(session, plan)
        assert len(dashboard.ordered(session, plan)) == 3
        assert dashboard.apply_report_defaults(session, plan, {'dashboard_widgets': default_specs()})
        assert [w.title for w in dashboard.ordered(session, plan)] == [s['title'] for s in default_specs()]
        assert plan.summary['dashboard_default_source'] == 'ai'
    # UI edits and their Undo own exactly the same widgets as before.
    initial = client.get('/api/plans/TESTAPI/dashboard').json()
    wid = initial['widgets'][0]['id']
    edited = client.put(f'/api/plans/TESTAPI/dashboard/{wid}', json=spec('demand')).json()
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        assert plan.summary['dashboard_customized']
        assert not dashboard.apply_report_defaults(session, plan, {'dashboard_widgets': default_specs()})
    assert client.post(f"/api/plans/TESTAPI/edits/{edited['edit_id']}/undo").json()['undone']
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] == initial['widgets']
    with scope() as session:
        assert not session.get(Plan, 'TESTAPI').summary.get('dashboard_customized')
    for widget in initial['widgets']:
        assert client.delete(f"/api/plans/TESTAPI/dashboard/{widget['id']}").status_code == 200
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        assert not dashboard.apply_report_defaults(session, plan, {'dashboard_widgets': default_specs()})
    assert client.get('/api/plans/TESTAPI/dashboard').json()['widgets'] == []
    assert 'health' in client.get('/api/plans/TESTAPI/dashboard').json()


def test_first_authored_defaults_can_complete_initial_snapshot_but_user_widgets_cannot():
    from copy import deepcopy
    from scoop.demo_reset import _same_mechanics
    before = {'plans': [{'id': 'P', 'summary': {}}], 'direction_items': [],
              'purchase_suggestions': [], 'watch_items': [{'id': 'old', 'origin': 'baseline'}]}
    after = deepcopy(before)
    after['plans'][0]['summary'] = {'dashboard_default_source': 'ai'}
    after['watch_items'] = [{'id': 'new', 'origin': 'baseline'}]
    assert _same_mechanics(before, after)
    after['plans'][0]['summary']['dashboard_customized'] = True
    assert not _same_mechanics(before, after)
