"""Small offline seed 93 checks without full generation, databases or AI."""
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd
import pytest

from scoop.synth import generate as generator
from scoop.synth import strawberry_challenge as challenge


@pytest.fixture
def catalog():
    return generator.build_catalog(np.random.default_rng(93), seed=93)


def test_catalog_memberships_and_distinct_comparators(catalog):
    stores, suppliers, products, nutrition, dimensions, tags, product_tags = catalog
    indices, parents = challenge.cells(products, product_tags)
    assert products.sku.iloc[indices].tolist() == ['IC006', 'IC061', 'IC062', 'IC063']
    assert products.iloc[indices].size_ml.tolist() == [75] * 4
    assert products.iloc[indices]['format'].tolist() == ['stick'] * 4
    assert products.iloc[indices].price_hkd.tolist() == [10., 9., 9.5, 10.]
    for dim in ('dairy', 'price_hkd'):
        values = product_tags.loc[product_tags.tag_id == dim].set_index('sku').loc[products.sku, 'value_num'].to_numpy()
        expected = np.digitize(values, np.quantile(values, [1/3, 2/3]), right=True) == 0
        np.testing.assert_array_equal(parents[f'band:{dim}:0'], expected)
    # Every parent and every pair has products that do not belong to the triple.
    key = challenge.answer_key(products, product_tags, stores)
    assert len(key['controls']['parent_and_pair_remainders']) == 6
    assert all(len(c['skus']) >= 3 for c in key['controls']['parent_and_pair_remainders'])
    # Each pair-only cohort and strawberry-only cohort is distinct and substantial.
    s, w, v = (parents[g] for g in challenge.GROUP_IDS)
    for mask in (s & w & ~v, s & v & ~w, w & v & ~s, s & ~w & ~v):
        assert mask.sum() >= 3
    assert len(products) == 75
    assert set(products.sku) == set(nutrition.sku) == set(product_tags.sku)
    assert set(product_tags.tag_id) == set(tags.id)
    assert set(tags.dimension_id) <= set(dimensions.id)
    assert set(products.supplier_id) <= set(suppliers.id)
    assert (products.price_hkd > products.cost_hkd).all()
    assert (products.cost_hkd > 0).all()
    for actual, repeat in zip(catalog, generator.build_catalog(np.random.default_rng(93), seed=93)):
        pd.testing.assert_frame_equal(actual, repeat)


def test_only_triple_cells_change_with_deterministic_sustained_ramp(catalog):
    stores, _, products, _, _, _, tags = catalog
    days = [date(2026, 7, 5) + timedelta(days=i) for i in range(59)]
    baseline = np.full((len(days), len(stores), len(products)), 100, dtype=np.int64)
    baseline[0] = 0
    orders = baseline.copy()
    originals = [f.copy(deep=True) for f in (stores, products, tags)]
    events = challenge.inject(orders, days, stores, products, tags)
    indices, _ = challenge.cells(products, tags)
    expected = baseline.copy()
    for di, day in enumerate(days):
        if challenge.START < day <= challenge.END:
            multiplier = 1 + .8 * min(1., (day-challenge.START).days/7)
            expected[di, :, indices] = int(np.floor(100 * multiplier + .5))
    np.testing.assert_array_equal(orders, expected)
    np.testing.assert_array_equal(orders[:2], baseline[:2])
    assert np.all(orders[days.index(challenge.FULL):days.index(challenge.END)+1, :, indices] == 180)
    np.testing.assert_array_equal(orders[-1], baseline[-1])
    control_indices = np.flatnonzero(~products.sku.isin(products.sku.iloc[indices]).to_numpy())
    np.testing.assert_array_equal(orders[:, :, control_indices], baseline[:, :, control_indices])
    assert orders.dtype == np.int64
    repeat = baseline.copy()
    pd.testing.assert_frame_equal(events, challenge.inject(repeat, days, stores, products, tags))
    np.testing.assert_array_equal(orders, repeat)
    for frame, original in zip((stores, products, tags), originals):
        pd.testing.assert_frame_equal(frame, original)
    assert len(events) == 1 and events.tag_id.isna().all() and events.sku.isna().all()
    assert json.loads(events.note.iloc[0])['group_ids'] == list(challenge.GROUP_IDS)


@pytest.mark.parametrize('seed', [42, 73, 91, 92])
def test_original_seed_catalogs_and_rng_state_unchanged(seed):
    original_rng, seeded_rng = np.random.default_rng(seed), np.random.default_rng(seed)
    for original, seeded in zip(generator.build_catalog(original_rng), generator.build_catalog(seeded_rng, seed=seed)):
        pd.testing.assert_frame_equal(original, seeded)
    np.testing.assert_array_equal(original_rng.integers(0, 10000, 30), seeded_rng.integers(0, 10000, 30))


@pytest.mark.parametrize('seed', [42, 73, 91, 92, 93])
def test_generation_hook_precedes_dc_and_only_runs_for_seed93(seed, monkeypatch):
    from scoop.synth import challenge as old91, combination_challenge as old92, compound_demo
    days = [date(2025, 7, 1), compound_demo.START, compound_demo.FULL, compound_demo.END]
    monkeypatch.setattr(generator, '_dates', lambda: days)
    monkeypatch.setattr(generator, 'build_weather', lambda *args, **kwargs: (pd.DataFrame(), pd.DataFrame(), None))
    monkeypatch.setattr(generator, 'build_demand', lambda rng, days, stores, products, tags, weather, **kwargs:
                        (np.full((len(days), len(stores), len(products)), 100, dtype=np.int64), pd.DataFrame(), pd.DataFrame()))
    old_calls = []
    monkeypatch.setattr(old91, 'inject', lambda *args: old_calls.append(91) or pd.DataFrame())
    monkeypatch.setattr(old92, 'inject', lambda *args: old_calls.append(92) or pd.DataFrame())
    actual_inject = compound_demo.inject
    new_calls = []
    def inject(*args):
        new_calls.append(93)
        return actual_inject(*args)
    monkeypatch.setattr(compound_demo, 'inject', inject)
    dc_calls = []
    def dc(rng, days, stores, products, suppliers, orders):
        dc_calls.append(True)
        expected = np.full_like(orders, 100)
        if seed == 93:
            tags = generator.build_catalog(np.random.default_rng(seed), seed=seed)[6]
            actual_inject(expected, days, stores, products, tags)
            assert np.any(expected != 100)
        np.testing.assert_array_equal(orders, expected)
        return orders.copy(), np.ones((len(days), len(products)), dtype=np.int64), pd.DataFrame()
    monkeypatch.setattr(generator, 'simulate_dc', dc)
    world = generator.generate(seed)
    assert dc_calls == [True]
    assert old_calls == ([seed] if seed in (91, 92) else [])
    assert new_calls == ([93] if seed == 93 else [])
    assert len(world.products) == (75 if seed == 93 else 60)
    assert len(world.events) == (4 if seed == 93 else 0)


def test_null_counterfactual_uses_same_seed93_catalog(monkeypatch):
    days = [date(2026, 7, 27)]
    monkeypatch.setattr(generator, '_dates', lambda: days)
    monkeypatch.setattr(generator, 'build_weather', lambda *args: (pd.DataFrame(), pd.DataFrame(), None))
    def demand(rng, days, stores, products, tags, weather, *, planted):
        assert not planted and len(products) == 75
        return np.full((1, len(stores), len(products)), 100, dtype=np.int64), pd.DataFrame(), pd.DataFrame()
    monkeypatch.setattr(generator, 'build_demand', demand)
    frame, _ = generator.null_orders(93)
    assert frame.sku.nunique() == 75 and (frame.ordered_units == 100).all()


def test_neutral_scenario():
    from scoop.demo_worlds import SCENARIOS
    scenario = next(s for s in SCENARIOS if s['seed'] == 93)
    from scoop.demo_config import DEMO_WEEK
    assert scenario['name'] == 'Demo warehouse' and scenario['default_week'] == DEMO_WEEK
    assert {'2026-07-20', '2026-07-27', '2026-08-03'} <= set(scenario['weeks'])
    assert not any(term in scenario['description'].lower() for term in ('strawberry', 'water', 'price', 'hx93', 'uplift'))
    assert any(s['seed'] == 92 for s in SCENARIOS)
