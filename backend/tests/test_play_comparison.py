"""The comparison is selected by warehouse space under a strict replay cap."""
from datetime import date

import pandas as pd
import pytest

from scoop import play, play_comparison


DAY = date(2026, 7, 13)


def _result(pallets, losses=0, baseline=None):
    summary = lambda p, l: {'avg_pallets': p, 'lost_units': l,
                            'stockout_sku_days': l, 'lost_margin': l * 2}
    base = baseline if baseline is not None else {'daily': ['rule'], 'per_sku': {'lost': [[0]]}}
    return {'summary': {'scoop': summary(pallets, losses), 'baseline': summary(10, 5)},
            'runs': {'scoop': {'daily': [pallets], 'per_sku': {'lost': [[losses]]}},
                     'baseline': base}}


def test_bisection_stops_within_two_percent_and_reuses_baseline(monkeypatch):
    actual = _result(5, 50)
    calls = []

    def simulate(pid, week, **kwargs):
        calls.append(kwargs)
        if not kwargs:
            return actual
        assert kwargs['_baseline_run'] is actual['runs']['baseline']
        return _result(20 * kwargs['_service_level'], 100 - int(100 * kwargs['_service_level']),
                       actual['runs']['baseline'])

    monkeypatch.setattr(play, 'simulate', simulate)
    result = play_comparison.prepare('P', DAY)
    matched = result['matched']
    assert result is not actual and 'matched' not in actual
    assert matched['status'] == 'matched'
    assert matched['relative_pallet_gap'] <= .02
    assert matched['simulation_count'] == len(calls) <= 6
    assert matched['summary']['baseline'] is actual['summary']['baseline']
    assert matched['runs']['scoop']['daily'] == [pytest.approx(matched['summary']['scoop']['avg_pallets'])]
    assert result['summary']['scoop']['avg_pallets'] == 5


def test_closest_measured_uses_space_even_when_loss_is_worse(monkeypatch):
    actual = _result(2, 0)
    def simulate(pid, week, **kwargs):
        if not kwargs:
            return actual
        service = kwargs['_service_level']
        return _result(9 if service == .5 else 8, 100 if service == .5 else 0,
                       actual['runs']['baseline'])
    monkeypatch.setattr(play, 'simulate', simulate)
    matched = play_comparison.prepare('P', DAY)['matched']
    assert matched['status'] == 'closest'
    assert matched['limit_reason'] == 'service_bounds'
    assert matched['service_level'] == .5
    assert matched['simulation_count'] == 3
    assert matched['summary']['scoop']['lost_units'] == 100


def test_automatic_policy_in_band_still_measures_explicit_service_candidates(monkeypatch):
    actual = _result(9.85, 0)
    def simulate(pid, week, **kwargs):
        if not kwargs:
            return actual
        service = kwargs['_service_level']
        return _result(4 if service == .5 else 10.02, 500, actual['runs']['baseline'])
    monkeypatch.setattr(play, 'simulate', simulate)
    matched = play_comparison.prepare('P', DAY)['matched']
    assert matched['simulation_count'] == 3
    assert matched['service_level'] == .98
    assert matched['relative_pallet_gap'] == pytest.approx(.002)
    # Selection remains based on space even when the closer policy loses more.
    assert matched['summary']['scoop']['lost_units'] == 500


def test_candidate_quantities_preserve_relative_and_absolute_edits(monkeypatch):
    from scoop import planning
    orders = pd.DataFrame([
        {'sku': 'A', 'suggested_cases': 5, 'capacity_cut_cases': 1, 'cases': 6},
        {'sku': 'B', 'suggested_cases': 5, 'capacity_cut_cases': 0, 'cases': 8},
    ])
    cohort = {'sku_factors': {}, 'cases_overrides': {'B': 8}}
    seen = []
    def suggest(as_of, directions, **kwargs):
        seen.append(kwargs)
        return pd.DataFrame([{'sku': 'A', 'final_cases': 7}, {'sku': 'B', 'final_cases': 8}])
    monkeypatch.setattr(planning, 'suggest_orders', suggest)
    inv = pd.Series({'A': 10, 'B': 20})
    transit = pd.DataFrame(columns=['sku', 'units', 'received_date', 'expected_date'])
    cases = play._candidate_week_cases(DAY, ['A', 'B'], orders, inv, transit,
                                       {'cohort_model': cohort}, .8, 'margin', {})
    assert cases == {'A': 9, 'B': 8}
    assert seen[0]['service_level'] == .8
    assert seen[0]['overrides'] == []
    assert seen[0]['position'].set_index('sku').on_hand_units.to_dict() == {'A': 10, 'B': 20}
    assert orders.cases.tolist() == [6, 8]
