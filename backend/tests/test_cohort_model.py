"""Focused offline tests of the cohort model's statistical and data contracts."""
from datetime import date, timedelta
from types import SimpleNamespace
import json

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scoop.algorithms import cohort_model
from scoop.algorithms.groups import Group
from scoop.models import Product, Promotion, Store, StoreOrder


def _units(effect=0.7, volume=100., affected=None):
    affected = set(affected or ('S0', 'S1', 'S2'))
    return [{'sku': f'S{i}', 'district': d, 'y': effect if f'S{i}' in affected else 0.,
             'v': 0.02 * 100 / volume, 'expected_recent': volume}
            for i in range(9) for d in ('north', 'south')]


def test_tree_is_deterministic_and_shrinks():
    units = _units()
    groups = [Group('candidate', 'Candidate', 'kind', ('S0', 'S1', 'S2'))]
    a = cohort_model.fit_units(units, groups)
    assert a == cohort_model.fit_units(units, groups)
    assert len(a['leaves']) == 2
    target = next(l for l in a['leaves'] if set(l['skus']) == {'S0', 'S1', 'S2'})
    assert target['split_p_values'][0] < .05
    assert 1 < a['sku_factors']['S0']['f50'] < np.exp(.7)
    assert a['sku_factors']['S0']['f10'] < a['sku_factors']['S0']['f50'] < a['sku_factors']['S0']['f90']
    assert json.dumps(a, allow_nan=False)


def test_partial_alignment_unaffected_sku_stays_near_control():
    units = _units(affected=('S0', 'S1', 'S3'))
    result = cohort_model.fit_units(units, [Group('cohort', 'Cohort', 'kind', ('S0', 'S1', 'S2'))])
    assert result['sku_factors']['S2']['f50'] == pytest.approx(1.)
    assert result['sku_factors']['S3']['f50'] == pytest.approx(result['sku_factors']['S0']['f50'])
    assert result['sku_factors']['S2']['f50'] < result['sku_factors']['S0']['f50']
    assert result['sku_factors']['S2']['f50'] < result['sku_factors']['S1']['f50']


def test_halved_volume_moves_toward_leaf():
    # Heterogeneity is learned from neighboring units; smaller inverse-variance
    # weight gives the individual observation less influence.
    units = _units(affected=('S0', 'S1', 'S2', 'S3'))
    groups = [Group('cohort', 'Cohort', 'kind', tuple(f'S{i}' for i in range(6)))]
    full = cohort_model.fit_units(units, groups)
    half_units = [dict(u, v=u['v'] * 2, expected_recent=u['expected_recent'] / 2)
                  if u['sku'] == 'S0' else u for u in units]
    half = cohort_model.fit_units(half_units, groups)
    full_u = next(u for u in full['units'] if u['sku'] == 'S0')
    half_u = next(u for u in half['units'] if u['sku'] == 'S0')
    full_leaf = next(l for l in full['leaves'] if l['id'] == full_u['leaf_id'])
    half_leaf = next(l for l in half['leaves'] if l['id'] == half_u['leaf_id'])
    assert half_u['leaf_weight'] >= full_u['leaf_weight']
    assert abs(half_u['m'] - half_leaf['posterior_mean']) < abs(full_u['m'] - full_leaf['posterior_mean'])


def test_null_noise_has_no_root_split_in_at_least_95_percent_of_weeks():
    rng = np.random.default_rng(9300)
    groups = [Group('g0', 'G0', 'kind', tuple(f'S{i}' for i in range(4))),
              Group('g1', 'G1', 'kind', tuple(f'S{i}' for i in range(4, 8)))]
    unsplit = 0
    for _ in range(20):
        rows = [{'sku': f'S{i}', 'district': area, 'y': float(rng.normal(0, .1)),
                 'v': .01, 'expected_recent': 100}
                for i in range(12) for area in ('a', 'b')]
        unsplit += len(cohort_model.fit_units(rows, groups)['leaves']) == 1
    assert unsplit >= 19


def test_no_admissible_split_and_zero_heterogeneity():
    result = cohort_model.fit_units(_units(effect=0., affected=set()), [])
    assert len(result['leaves']) == 1
    assert all(f['f50'] == 1 for f in result['sku_factors'].values())
    assert cohort_model.fit_units([], [])['sku_factors'] == {}
    assert cohort_model.project_level([1, 2], 3) == [2., 2., 2.]


def test_read_only_preparation_promotion_winsorisation_and_missing(monkeypatch):
    engine = create_engine('sqlite://')
    for table in (Product.__table__, Store.__table__, StoreOrder.__table__, Promotion.__table__):
        table.create(engine)
    with Session(engine) as session:
        session.add(Store(id='A', name='A', district='north', format='standard', lat=0, lon=0, size_factor=1))
        for sku in ('S0', 'S1', 'S2'):
            session.add(Product(sku=sku, name=sku, brand='X', format='stick', size_ml=100,
                                units_per_case=10, cases_per_pallet=10, price_hkd=10, cost_hkd=5,
                                supplier_id='X', moq_cases=1, launch_date=date(2020, 1, 1),
                                status='active', description='X'))
        plan = SimpleNamespace(week_start=date(2026, 7, 27))
        start = plan.week_start - timedelta(days=70)
        expected = []
        spike = plan.week_start - timedelta(days=4)
        promo = plan.week_start - timedelta(days=3)
        for day in (start + timedelta(days=i) for i in range(70)):
            for sku in ('S0', 'S1', 'S2'):
                value = 10000 if sku == 'S0' and day == spike else 100
                session.add(StoreOrder(date=day, store_id='A', sku=sku, ordered_units=value, shipped_units=value))
                if not (sku == 'S2' and day == spike):
                    expected.append({'date': pd.Timestamp(day), 'store_id': 'A', 'sku': sku,
                                     'mean': 100., 'model_version': 'issued'})
        session.add(Promotion(id='P', sku='S0', start_date=promo, end_date=promo,
                              discount_pct=10., note='X'))
        session.commit()
        from scoop.ai import exploration_tools
        monkeypatch.setattr(cohort_model, 'current_expectations', lambda _: pd.DataFrame(expected))
        monkeypatch.setattr(exploration_tools, '_groups', lambda _: {})
        result = cohort_model.fit(plan, session)
        s0 = next(u for u in result['units'] if u['sku'] == 'S0')
        assert s0['promotion_exclusions'] == [promo.isoformat()]
        assert s0['winsorised'] and s0['recent_A'] < 10000
        assert s0['recent_days'] == 13 and s0['baseline_days'] == 56
        assert not any(u['sku'] == 'S2' for u in result['units'])
        assert result['method']['skipped_units'][0]['reason'] == 'missing_rows_or_short_window'
        series = result['leaves'][0]['daily']
        assert next(r for r in series if r['date']==spike.isoformat())['requested_units']==10100
        assert next(r for r in series if r['date']==promo.isoformat())['requested_units']==100
        assert not session.dirty and not session.new and not session.deleted
        json.dumps(result, allow_nan=False)
    engine.dispose()


def test_short_promotion_filtered_baseline_is_used():
    week = date(2026, 7, 27)
    first = week - timedelta(days=70)
    rows = [(first + timedelta(days=i), 'A', 'S0', 100) for i in range(70)]
    expected = pd.DataFrame([{'date': d, 'store_id': store, 'sku': sku, 'mean': 100.}
                             for d, store, sku, _ in rows])
    promotion = SimpleNamespace(sku='S0', start_date=first, end_date=first+timedelta(days=48))
    result = cohort_model.fit_observations(week, rows, expected, {'A': 'north'}, ['S0'], [promotion], [])
    assert len(result['units']) == 1
    assert result['units'][0]['baseline_days'] == 7
    assert result['sku_factors']['S0']['f50'] == pytest.approx(1.)


def test_retrained_expectations_absorb_change_without_stored_factors():
    week = date(2026, 7, 27)
    first = week - timedelta(days=70)
    rows = [(first+timedelta(days=i), 'A', f'S{j}',
             200 if i >= 56 and j < 3 else 100) for i in range(70) for j in range(9)]
    original = pd.DataFrame([{'date': d, 'store_id': store, 'sku': sku, 'mean': 100.}
                             for d, store, sku, _ in rows])
    absorbed = original.copy()
    absorbed['mean'] = [float(a) for _, _, _, a in rows]
    args = ({'A': 'north'}, [f'S{j}' for j in range(9)], [],
            [Group('cohort', 'Cohort', 'kind', ('S0', 'S1', 'S2'))])
    before = cohort_model.fit_observations(week, rows, original, *args)
    after = cohort_model.fit_observations(week, rows, absorbed, *args)
    assert before['sku_factors']['S0']['f50'] > 1.5
    assert after['sku_factors']['S0']['f50'] == pytest.approx(1.)
