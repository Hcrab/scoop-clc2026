"""Assistant cohort edits use the same persisted context and exact undo as the API."""
from datetime import datetime

import pandas as pd
from sqlalchemy import select, func

from test_api_state import api
from scoop.ai import chat, tools
from scoop.api.cohorts import order_snapshot
from scoop.algorithms.groups import Group
from scoop.cohort_context import load_overrides
from scoop.models import Decision, Plan


def cohort_fixture(api, monkeypatch):
    _, scope, _, planning = api
    from scoop.ai import exploration_tools
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {
        'family:fruit': Group('family:fruit', 'Fruit', 'family', ('IC001',))})
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.summary = {**plan.summary, 'cohort_model': {'leaves': [
            {'id': 'FRUIT-COHORT', 'tag_path': [{'id': 'family:fruit', 'included': True}],
             'districts': ['Kowloon'], 'skus': ['IC001']}], 'sku_factors': {}},
            'cohort_cards': [{'id': 'FRUIT-COHORT', 'name': 'Fruit summer group',
                              'tag_path': [{'id': 'family:fruit', 'included': True}],
                              'districts': ['Kowloon'], 'skus': ['IC001']}]}

    def orders(as_of, directions, **kwargs):
        changed = bool(kwargs.get('overrides'))
        frame = pd.DataFrame([{'sku': 'IC001', 'order_date': as_of, 'pdays': 10,
            'demand_p10': 20., 'demand_p50': 30., 'demand_p90': 40.,
            'adjustment': .8 if changed else 1., 'critical_ratio': .8,
            'target_units': 40., 'on_hand_units': 10, 'on_order_units': 0,
            'inventory_position': 10, 'suggested_cases': 2 if changed else 3,
            'capacity_cut_cases': 0}])
        frame.attrs['cohort_model'] = {'leaves': [], 'sku_factors': {}}
        return frame
    monkeypatch.setattr(planning, 'suggest_orders', orders)


def test_tool_edit_persists_recomputes_and_undoes_exactly(api, monkeypatch):
    _, scope, _, _ = api
    cohort_fixture(api, monkeypatch)
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.stage = 'execute'
        plan.locked_at = datetime.now()
        before = order_snapshot(session, plan)
        visible = tools.context(session, plan)
        assert visible['cohorts'][0]['id'] == 'FRUIT-COHORT'
        assert visible['active_overrides'] == []
        assert 'directions' not in visible
        assert 'interpretation' not in visible['findings'][0]
        result, action = tools.execute('set_override', {
            'cohort': 'FRUIT-COHORT', 'type': 'ends_on', 'value': '2026-08-10',
            'note': 'Summer one-off'}, session, plan, 'discover')
        assert action['type'] == 'edit' and action['edit_id'] == result['edit_id']
        assert action['before']['orders'] == [{'sku':'IC001','cases':3,'factor':before[0]['adjustment']}]
        assert 'summary' not in action['before']
        assert action['affected_orders'][0]['before'] == 3
        assert action['affected_orders'][0]['after'] == 2
        assert action['order_change']=={'product_count':1,'before_cases':3,'after_cases':2,'delta_cases':-1}
        assert plan.stage == 'direction'
        assert load_overrides(session)[0]['value'] == '2026-08-10'
        edit_id = result['edit_id']
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        restored, undo = tools.execute('undo_edit', {'edit_id': edit_id}, session, plan, 'direction')
        assert undo['type'] == 'undo' and restored['undone']
        assert order_snapshot(session, plan) == before
        assert load_overrides(session) == []
        assert plan.stage == 'execute' and plan.locked_at is not None
        assert session.scalar(select(func.count()).select_from(Decision)) == 1


def test_scripted_end_date_uses_catalog_match_and_exact_undo(api, monkeypatch):
    client, scope, _, _ = api
    cohort_fixture(api, monkeypatch)
    saved = client.post('/api/plans/TESTAPI/chat', json={
        'message': 'The fruit thing is a summer one-off, it ends 10 Aug',
        'stage': 'discover'}).json()
    assert saved['actions'][0]['type'] == 'edit', saved
    edit_id = saved['actions'][0]['edit_id']
    with scope() as session:
        assert load_overrides(session)[0]['value'] == '2026-08-10'
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['suggested_cases'] == 2
    undone = client.post('/api/plans/TESTAPI/chat', json={
        'message': f'Undo edit {edit_id}', 'stage': 'discover'}).json()
    assert 'actions' in undone, undone
    assert undone['actions'][0]['type'] == 'undo', undone
    with scope() as session:
        assert load_overrides(session) == []
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['suggested_cases'] == 3


def test_chat_context_indexes_report_queries_without_copying_result_tables(api, monkeypatch):
    _, scope, _, _ = api
    cohort_fixture(api, monkeypatch)
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.summary = {**plan.summary, 'weekly_review': {'queries': [
            {'id': 'Q1', 'name': 'query_group', 'args': {'group_id': 'family:fruit'},
             'result': {'rows': ['large historic result'] * 10000}}]}}
        context = tools.context(session, plan)
        assert context['review_evidence'] == [
            {'id': 'Q1', 'name': 'query_group', 'args': {'group_id': 'family:fruit'}}]
