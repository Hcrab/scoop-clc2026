"""Focused checks for weather features, cohort uncertainty/trace, and summer cost."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scoop.algorithms import cohort_model, forecast, replenish, runs
from scoop.algorithms.groups import Group
from scoop.cohort_cards import _drilldown, build_cards


def test_weather_interactions_use_catalog_dairy_terciles_and_issued_weather(monkeypatch):
    monkeypatch.setattr(forecast, '_holidays', lambda: set())
    products = pd.DataFrame({'sku': ['A', 'B', 'C'], 'format': ['stick', 'cup', 'tub'],
                             'family': ['fruit'] * 3, 'dairy': [.1, .5, .9],
                             'richness': [.2] * 3, 'sweetness': [.2] * 3,
                             'choc_coated': [0] * 3, 'low_sugar': [0] * 3,
                             'price_hkd': [10.] * 3, 'sugar_100ml': [10.] * 3})
    static = SimpleNamespace(products=products,
        stores=pd.DataFrame({'store_id': ['S'], 'district': ['North'], 'size_factor': [1.]}),
        promo_frame=lambda dates: pd.DataFrame(columns=['date', 'sku', 'promo_disc']))
    dates = pd.DatetimeIndex(['2026-07-01'])
    issued = pd.DataFrame({'date': dates, 'tmax': [31.], 'rain_mm': [0.]})
    frame = forecast.build_features(static, dates, weather=issued).set_index('sku')
    for sku, dairy_column, format_column in [('A', 'water', 'stick'),
                                              ('B', 'middle', 'cup'), ('C', 'rich', 'tub')]:
        assert frame.loc[sku, f'tmax_x_dairy_{dairy_column}'] == 31
        assert frame.loc[sku, f'tmax_x_format_{format_column}'] == 31
        assert sum(frame.loc[sku, f'tmax_x_dairy_{part}'] for part in ('water','middle','rich')) == 31
    assert runs.LOGIC_VERSION.endswith('v2')
    assert 'tmax_x_format_cup' in forecast.FEATURES


def _history(noisy=False):
    week = date(2026, 7, 27)
    first = week - timedelta(days=70)
    rows = []
    expected = []
    for i in range(70):
        for sku_index in range(9):
            for district in ('North', 'South'):
                sku = f'S{sku_index}'
                day = first + timedelta(days=i)
                baseline_offset = (30 if (i // 7) % 2 else -30) if noisy and i < 56 else 0
                amount = 100 + baseline_offset + (50 if i >= 56 and sku_index < 3 else 0)
                rows.append((day, district, sku, amount))
                expected.append({'date': day, 'store_id': district, 'sku': sku, 'mean': 100.})
    groups = [Group('fruit', 'Strawberry', 'flavour', tuple(f'S{i}' for i in range(3)))]
    args = (week, rows, pd.DataFrame(expected), {'North': 'North', 'South': 'South'},
            [f'S{i}' for i in range(9)], [], groups)
    return args, groups


def test_measured_error_increases_variance_without_changing_prepared_point_estimate():
    quiet, _ = _history()
    noisy, _ = _history(noisy=True)
    a = cohort_model.fit_observations(*quiet)
    b = cohort_model.fit_observations(*noisy)
    au = next(u for u in a['units'] if u['sku'] == 'S0')
    bu = next(u for u in b['units'] if u['sku'] == 'S0')
    assert bu['y'] == pytest.approx(au['y'])
    assert au['forecast_error_v'] == 0
    assert bu['forecast_error_v'] > 0
    assert bu['v'] > au['v']
    assert 'baseline seven-day' in b['method']['forecast_error_variance']


def test_drilldown_siblings_sum_to_parent_and_district_membership():
    args, groups = _history()
    result = cohort_model.fit_observations(*args)
    leaf = next(l for l in result['leaves'] if any(p['included'] for p in l['tag_path']))
    trace = _drilldown(leaf, {g.id: g for g in groups})
    assert len(trace['steps']) == len(leaf['tag_path'])
    parent = trace['root']['daily']
    for step in trace['steps']:
        child = {x['date']: x for x in step['daily']}
        rest = {x['date']: x for x in step['rest_daily']}
        for row in parent:
            for key in ('requested_units', 'expected_units'):
                assert child.get(row['date'], {}).get(key, 0) + rest.get(row['date'], {}).get(key, 0) == pytest.approx(row[key])
        parent = step['daily']

    # A two-level path proves the district sibling is scoped to its product parent.
    result['leaves'] = [{'tag_path': [{'id': 'fruit', 'included': True},
                                      {'id': 'district:North', 'included': False}]}]
    chart_rows = {(u['sku'], u['district']): {date(2026,7,1): (1., 2.)} for u in result['units']}
    cohort_model._attach_drilldowns(result, chart_rows, groups)
    fruit, district = result['leaves'][0]['drilldown']['steps']
    assert fruit['sku_count'] == 3 and fruit['rest_sku_count'] == 6
    assert fruit['daily'][0]['requested_units'] == 6
    assert district['daily'][0]['requested_units'] == district['rest_daily'][0]['requested_units'] == 3
    assert district['sku_count'] == district['rest_sku_count'] == 3


def test_normal_fit_to_card_projects_saved_drilldown_without_rescoring():
    args, groups = _history()
    result = cohort_model.fit_observations(*args)
    skus = [f'S{i}' for i in range(9)]
    orders = pd.DataFrame({'sku': skus, 'final_cases': [5] * 9,
        'demand_p10': [80.] * 9, 'demand_p50': [100.] * 9, 'demand_p90': [120.] * 9,
        'inventory_position': [0] * 9, 'projected_pallets': [1.] * 9})
    orders.attrs['capacity_pallets'] = 10.
    baseline = orders.copy()
    baseline['final_cases'] = 4
    products = pd.DataFrame({'sku': skus, 'units_per_case': [10] * 9,
        'cases_per_pallet': [10] * 9, 'price_hkd': [10.] * 9, 'cost_hkd': [6.] * 9})
    cards = build_cards(result, orders, baseline, products, {g.id: g for g in groups},
                        {sku: sku for sku in skus})
    assert cards
    assert all(card['drilldown']['root']['daily'] for card in cards)
    assert all(len(card['drilldown']['steps']) == len(card['tag_path']) for card in cards)


def test_summer_cost_and_marginal_allocation_use_same_excess_cost(monkeypatch):
    assert replenish.HOLDING_RATE == .025
    assert replenish.critical_ratio(10, 6) == pytest.approx(4 / (4 + .025 * 6))
    assert replenish.critical_ratio(10, 6, .8) == .8
    seen = []
    original_cdf = replenish.norm.cdf
    def capture(*args, **kwargs):
        seen.append(True)
        return original_cdf(*args, **kwargs)
    monkeypatch.setattr(replenish.norm, 'cdf', capture)
    items = [replenish.SkuInput('A', 100, 9, 10, 6, 10, 10, 1, 0, 0, 2)]
    plan = replenish.plan_orders(items, np.linspace(.8, 1.2, 21), 0)
    assert seen and plan.iloc[0].capacity_cut_cases > 0
    assert plan.iloc[0].excess_unit_cost_rate == .025
    assert 'summer carryover/markdown' in plan.iloc[0].excess_unit_cost_basis
