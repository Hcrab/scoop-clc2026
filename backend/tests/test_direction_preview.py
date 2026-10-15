"""Direction preview calculates consequences without saving a planning edit."""
from copy import deepcopy
from contextlib import contextmanager

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from scoop.algorithms.replenish import critical_ratio
from scoop.demo_gate import DemoGateMiddleware
from scoop.models import Decision, Plan, PurchaseSuggestion
from test_api_state import api


def test_two_targets_are_read_only_and_apply_matches_preview(api, monkeypatch):
    client, scope, _, planning = api
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.stage = 'direction'
        plan.summary = {'cohort_model': {'sku_factors': {'IC001': {'f50': 1.4}},
                                         'cases_overrides': {}, 'leaves': [],
                                         'applied_overrides': [{'id': 'saved-context'}]},
                        'flow': {'status': 'saved'}, 'simulation': {'status': 'saved'}}
        saved_summary = deepcopy(plan.summary)
        original_order = session.scalar(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == plan.id))
        original_cases = original_order.suggested_cases
        original_level = plan.service_level
        original_goal = plan.goal
        original_decisions = session.scalar(select(func.count()).select_from(Decision))

    calls = []
    preview_peak = None

    def suggest(as_of, directions, *, service_level, goal, cohort_result=None, overrides=None):
        calls.append((service_level, goal, deepcopy(cohort_result), overrides))
        if cohort_result is not None:
            assert cohort_result['sku_factors']['IC001']['f50'] == 1.4
            assert overrides == []
        count = 4 if service_level is None else round(service_level * 10)
        frame = pd.DataFrame([{'sku': 'IC001', 'order_date': as_of, 'pdays': 10,
                               'demand_p10': 20., 'demand_p50': 30., 'demand_p90': 40.,
                               'adjustment': 1.4, 'critical_ratio': service_level or .8,
                               'target_units': 40., 'on_hand_units': 10, 'on_order_units': 0,
                               'inventory_position': 10, 'suggested_cases': count,
                               'capacity_cut_cases': 0, 'final_cases': count,
                               'projected_pallets': 12. + count / 10}])
        frame.attrs.update(cohort_model=cohort_result or {'leaves': [], 'cases_overrides': {}},
                           capacity_pallets=10., inherited_peak_pallets=12.)
        return frame

    monkeypatch.setattr(planning, 'suggest_orders', suggest)
    monkeypatch.setattr(planning.cohort_model, 'fit',
                        lambda *_: pytest.fail('saved fit must be reused'))
    for level, expected in [(None, 4), (.5, 5), (.98, 10)]:
        response = client.post('/api/plans/TESTAPI/direction-preview',
                               json={'service_level': level})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['service_level'] == level
        assert data['cases'] == expected
        assert data['projected_peak_pallets'] == pytest.approx(12. + expected / 10)
        assert data['capacity_pallets'] == 10.
        assert data['inherited_peak_pallets'] == 12.
        assert data['inherited_excess_pallets'] == 2.
        assert data['incremental_excess_pallets'] == pytest.approx(expected / 10)
        assert data['auto_service_level'] == pytest.approx(critical_ratio(20, 10))
        with scope() as session:
            plan = session.get(Plan, 'TESTAPI')
            order = session.scalar(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == plan.id))
            assert (plan.summary, plan.service_level, plan.goal, plan.stage) == (
                saved_summary, original_level, original_goal, 'direction')
            assert order.suggested_cases == original_cases
            assert session.scalar(select(func.count()).select_from(Decision)) == original_decisions
        if level == .98:
            preview_peak = data['projected_peak_pallets']

    assert all(call[2] == saved_summary['cohort_model'] and call[3] == [] for call in calls)
    assert client.post('/api/plans/TESTAPI/direction-preview',
                       json={'service_level': .99}).status_code == 422
    applied = client.put('/api/plans/TESTAPI/goal',
                         json={'goal': 'margin', 'service_level': .98})
    assert applied.status_code == 200, applied.text
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        order = session.scalar(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == plan.id))
        assert order.suggested_cases == 10
        assert plan.service_level == .98
    assert calls[-1][0] == .98
    assert 12. + round(calls[-1][0] * 10) / 10 == pytest.approx(preview_peak)


def test_automatic_mean_respects_goal_default(api, monkeypatch):
    client, scope, _, planning = api
    with scope() as session:
        plan = session.get(Plan, 'TESTAPI')
        plan.goal = 'fill_rate'
    def suggest(*args, **kwargs):
        frame = pd.DataFrame([{'final_cases': 2, 'projected_pallets': 1.}])
        frame.attrs.update(capacity_pallets=10., inherited_peak_pallets=.5)
        return frame
    monkeypatch.setattr(planning, 'suggest_orders', suggest)
    response = client.post('/api/plans/TESTAPI/direction-preview', json={'service_level': None})
    assert response.status_code == 200, response.text
    assert response.json()['auto_service_level'] == pytest.approx(.97)
    assert response.json()['service_level'] is None


def test_only_exact_preview_post_is_classified_read_only():
    observed = []
    class Gate:
        @contextmanager
        def activity(self, **kwargs):
            observed.append(kwargs['read_only'])
            yield
    app = FastAPI()
    @app.post('/api/plans/{pid}/direction-preview')
    def preview(pid: str):
        return {'ok': True}
    @app.post('/api/plans/{pid}/direction-preview-extra')
    def other(pid: str):
        return {'ok': True}
    app.add_middleware(DemoGateMiddleware, activity_gate=Gate())
    with TestClient(app) as client:
        assert client.post('/api/plans/P/direction-preview').status_code == 200
        assert client.post('/api/plans/P/direction-preview-extra').status_code == 200
    assert observed == [True, False]
