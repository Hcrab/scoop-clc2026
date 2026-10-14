"""Controlled table fixtures for the standalone scan; no server or model fitting."""
from datetime import date, timedelta
from itertools import product
import json
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scoop.ai import exploration_tools
from scoop.algorithms.groups import Group
from scoop.algorithms import trend_scan
from scoop.models import Product, Store, StoreOrder


@pytest.fixture
def tables(monkeypatch):
    engine = create_engine('sqlite://')
    for table in (Product.__table__, Store.__table__, StoreOrder.__table__):
        table.create(engine)
    session = Session(engine)
    session.add_all([Store(id=f'S{i}', name=f'Store {i}', district=f'D{i}',
                           format='standard', lat=22., lon=114., size_factor=1.) for i in range(2)])
    cells = list(product((0, 1), repeat=3))
    sku_cells = {f'P{i:02}': cell for i, cell in enumerate(cells * 3)}
    for sku in sku_cells:
        session.add(Product(sku=sku, name=sku, brand='Fixture', format='stick', size_ml=100,
                            units_per_case=10, cases_per_pallet=10, price_hkd=20, cost_hkd=10,
                            supplier_id='fixture', moq_cases=3, launch_date=date(2020, 1, 1),
                            status='active', description='Controlled table'))
    catalog = [Group(f'{dim}:{value}', f'{dim} {value}', dim,
                     tuple(s for s, cell in sku_cells.items() if cell[axis] == value))
               for axis, dim in enumerate(('a', 'b', 'c')) for value in (0, 1)]
    catalog.append(Group('alias:a0', 'Alias for A0', 'alias', catalog[0].skus))
    rng = np.random.default_rng(123)
    expected, orders = [], []
    plan = SimpleNamespace(week_start=date(2026, 7, 13))
    for day in pd.date_range(plan.week_start - timedelta(days=70), plan.week_start):
        common = int(rng.integers(-5, 6))
        for store in ('S0', 'S1'):
            for sku, cell in sku_cells.items():
                units = 100 + common + int(rng.integers(-3, 4))
                if day.date() >= plan.week_start - timedelta(days=14) and cell == (0, 0, 0):
                    units += 100
                # High current noise, no persistent shift, in a separate cohort.
                if day.date() >= plan.week_start - timedelta(days=14) and cell == (1, 1, 1):
                    units += int(rng.choice((-80, 80)))
                if day.date() == plan.week_start:
                    units = 1_000_000_000
                orders.append(StoreOrder(date=day.date(), store_id=store, sku=sku,
                                         ordered_units=units, shipped_units=units))
                expected.append({'date': day, 'store_id': store, 'sku': sku, 'mean': 100.,
                                 'model_version': 'issued-fixture'})
    session.add_all(orders)
    session.commit()
    frame = pd.DataFrame(expected)
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {g.id: g for g in catalog})
    monkeypatch.setattr(exploration_tools, '_expectations', lambda _: frame.copy())
    yield session, plan, frame, catalog, sku_cells
    session.close()
    engine.dispose()


def test_concentrated_triple_and_parent_evidence(tables):
    session, plan, _, _, cells = tables
    result = trend_scan.scan(session, plan)
    triple = frozenset(s for s, c in cells.items() if c == (0, 0, 0))
    winners = [r for r in result['items'] if frozenset(r['skus']) == triple]
    assert result['status'] == 'ready' and winners
    item = winners[0]
    assert item['kind'] == 'combination' and len(item['group_ids']) == 3
    assert item['level'] == 'clear' and item['direction'] == 'up'
    assert item['deviation_pct'] == pytest.approx(100, abs=2)
    assert len(item['parents']) == 3
    assert all(p['deviation_pct'] < item['deviation_pct'] - 30 for p in item['parents'])
    assert item['checks']['distinct_from_parents']
    assert item['checks']['calibration_days'] == 56
    assert item['checks']['persistence'] == 1
    assert len(item['series']) == 28
    assert result['items'].index(item) < 10
    noisy = frozenset(s for s, c in cells.items() if c == (1, 1, 1))
    assert all(r['score'] < item['score'] for r in result['items'] if frozenset(r['skus']) == noisy)
    stable = frozenset(s for s, c in cells.items() if c == (1, 0, 1))
    assert not any(frozenset(r['skus']) == stable for r in result['items'])
    assert not session.dirty and not session.new and not session.deleted
    json.dumps(result, allow_nan=False)


def test_cutoff_dedup_repeatability_and_family_before_selection(tables):
    session, plan, frame, catalog, cells = tables
    first = trend_scan.scan(session, plan)
    second = trend_scan.scan(session, plan)
    assert first == second
    assert first['window_end'] == '2026-07-12'
    assert max(row['requested_units'] for item in first['items'] for row in item['series']) < 1_000_000
    keys = [(tuple(item['skus']), tuple(item['districts'])) for item in first['items']]
    assert len(keys) == len(set(keys))
    assert any(item['checks']['equivalent_labels'] for item in first['items'])
    # Full unique 1/2/3-member family, for all districts and each district.
    assert first['tested_count'] == len(trend_scan._candidates({g.id:g for g in catalog}, set(cells))) * 3
    assert first['tested_count'] > len(first['items'])
    assert all(i['checks']['family_tested_count'] == first['tested_count'] for i in first['items'])
    assert all(i['q_value'] >= i['checks']['approximate_p_value'] for i in first['items'])


def test_zero_missing_expected_and_missing_actual_are_safe(tables, monkeypatch):
    session, plan, frame, _, _ = tables
    monkeypatch.setattr(exploration_tools, '_expectations', lambda _: frame.assign(mean=0))
    result = trend_scan.scan(session, plan)
    assert result['status'] == 'unavailable' and result['items'] == []
    recent_only = frame[frame.date >= pd.Timestamp('2026-07-10')]
    monkeypatch.setattr(exploration_tools, '_expectations', lambda _: recent_only)
    assert trend_scan.scan(session, plan)['tested_count'] == 0
    monkeypatch.setattr(exploration_tools, '_expectations', lambda _: frame[frame.sku != 'P00'])
    result = trend_scan.scan(session, plan)
    assert all('P00' not in item['skus'] or item['sku_count'] >= 20 for item in result['items'])
    json.dumps(result, allow_nan=False)
    monkeypatch.setattr(exploration_tools, '_expectations', lambda _: frame)
    session.query(StoreOrder).filter(StoreOrder.date == date(2026, 7, 10)).delete()
    session.commit()
    assert trend_scan.scan(session, plan)['tested_count'] == 0


def test_same_dimension_excluded_and_superset_alias_canonical():
    catalog = {g.id:g for g in [Group('a:one', 'A', 'a', ('1','2','3','4')),
                               Group('a:two', 'B', 'a', ('1','2','3','5')),
                               Group('b:one', 'C', 'b', ('1','2','3','4'))]}
    candidates = trend_scan._candidates(catalog, set('12345'))
    assert len(candidates) == 3
    for _, definition in candidates:
        for ids in [definition['ids'], *definition['aliases']]:
            assert len({catalog[g].dimension for g in ids}) == len(ids)


def test_serial_variation_and_multiple_comparison_math():
    correlated = np.repeat(np.array([-1., 1., -1., 1., -1., 1., -1., 1.]), 7)
    assert trend_scan._long_run_variance(correlated) > np.var(correlated) * 2
    assert trend_scan._adjust([.01, .2, .03]).tolist() == pytest.approx([.055, .3666666667, .0825])
    stable = np.full(70, 1000.)
    recent = stable.copy(); recent[-14:] = 1500.
    clean = trend_scan._measure(recent, stable, np.ones(70, dtype=bool), np.ones(70))
    noisy = recent.copy(); noisy[-14:] += np.tile([-450, 450], 7)
    noisy_stats = trend_scan._measure(noisy, stable, np.ones(70, dtype=bool), np.ones(70))
    assert noisy_stats['statistic'] < clean['statistic']


def test_representative_vectorized_runtime(tables, monkeypatch):
    session, plan, frame, _, cells = tables
    # Ten dimensions with overlapping halves produce thousands of label choices,
    # rather than a hard-coded target list. Same-SKU aliases collapse before testing.
    rng = np.random.default_rng(2026)
    catalog = [Group(f'd{dim}:{tag}', f'Dimension {dim} tag {tag}', f'd{dim}',
                     tuple(s for s in cells if rng.random() < .65))
               for dim in range(10) for tag in range(3)]
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {g.id:g for g in catalog})
    began = perf_counter()
    result = trend_scan.scan(session, plan)
    elapsed = perf_counter() - began
    assert result['tested_count'] > 1000 and len(result['items']) <= 40
    assert elapsed < 15, f'Controlled 30-tag / 24-SKU / 2-store scan took {elapsed:.2f}s'
