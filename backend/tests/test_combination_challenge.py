"""Small offline seed92 checks, with no world switch or paid assistant calls."""
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd
import pytest

from scoop.synth import generate as generator
from scoop.synth import combination_challenge as challenge


@pytest.fixture
def catalog():
    return generator.build_catalog(np.random.default_rng(92))


def test_exact_catalog_terciles_and_private_memberships(catalog):
    stores, _, products, nutrition, _, _, tags = catalog
    key = challenge.answer_key(products, nutrition, tags, stores)
    assert key['relationships'][0]['skus'] == ['IC007', 'IC008', 'IC014', 'IC051']
    assert key['relationships'][1]['skus'] == ['IC004', 'IC005', 'IC016', 'IC034', 'IC038', 'IC042', 'IC047', 'IC053']
    groups, parents, edges = challenge.cells(products, nutrition, tags)
    assert all(len(indices) >= 3 for indices in groups.values())
    for dim in ('price_hkd', 'sugar_100ml'):
        values = tags.loc[tags.tag_id == dim].set_index('sku').loc[products.sku, 'value_num'].to_numpy()
        np.testing.assert_array_equal(edges[dim], np.quantile(values, [1/3, 2/3]))
        expected = np.digitize(values, edges[dim], right=True) == (2 if dim == 'price_hkd' else 0)
        np.testing.assert_array_equal(parents['premium_price' if dim == 'price_hkd' else 'lower_sugar'], expected)
    energy = nutrition.kcal.to_numpy() / nutrition.serving_ml.to_numpy() * 100
    np.testing.assert_array_equal(parents['lower_kcal'], np.digitize(energy, np.quantile(energy, [1/3, 2/3]), right=True) == 0)


def test_interventions_only_target_intersections_districts_and_dates(catalog):
    stores, _, products, nutrition, _, _, tags = catalog
    days = [date(2026, 7, 5) + timedelta(days=i) for i in range(60)]
    baseline = np.full((len(days), len(stores), len(products)), 20, dtype=np.int64)
    baseline[0] = 0
    orders = baseline.copy()
    before = [frame.copy(deep=True) for frame in (stores, products, nutrition, tags)]
    events = challenge.inject(orders, days, stores, products, nutrition, tags)
    expected = baseline.copy()
    for relationship in challenge.answer_key(products, nutrition, tags, stores)['relationships']:
        start = date.fromisoformat(relationship['start_date'])
        full = date.fromisoformat(relationship['full_effect_date'])
        si = np.flatnonzero(stores.district.isin(relationship['districts']).to_numpy())
        pi = np.flatnonzero(products.sku.isin(relationship['skus']).to_numpy())
        for di, day in enumerate(days):
            if start < day <= challenge.END:
                mult = 1 + relationship['effect']['peak_fraction'] * min(1., (day - start).days / (full - start).days)
                expected[np.ix_([di], si, pi)] = int(np.floor(20 * mult + .5))
        plateau = days.index(full)
        assert np.all(orders[np.ix_([plateau], si, pi)] == (33 if relationship['id'] == 'HX92A' else 31))
        assert relationship['negative_controls']['parent_only']
    np.testing.assert_array_equal(orders, expected)
    assert orders.dtype == np.int64 and orders.min() >= 0
    for frame, original in zip((stores, products, nutrition, tags), before):
        pd.testing.assert_frame_equal(frame, original)
    repeat = baseline.copy()
    pd.testing.assert_frame_equal(events, challenge.inject(repeat, days, stores, products, nutrition, tags))
    np.testing.assert_array_equal(orders, repeat)
    assert [json.loads(note)['effect']['peak_fraction'] for note in events.note] == [.65, .55]
    assert not products.description.str.contains('HX92|premium|combination', case=False).any()


@pytest.mark.parametrize('seed', [42, 73, 91, 92])
def test_hook_before_dc_and_original_seed_paths(seed, monkeypatch):
    # Exercise the real entry point cheaply, without repeated full world generation.
    import scoop.synth.challenge as previous_challenge
    days = [date(2025, 7, 1), date(2026, 7, 27)]
    monkeypatch.setattr(generator, '_dates', lambda: days)
    monkeypatch.setattr(generator, 'build_weather', lambda rng, days: (pd.DataFrame(), pd.DataFrame(), None))
    def demand(rng, days, stores, products, tags, weather):
        return np.full((len(days), len(stores), len(products)), 20, dtype=np.int64), pd.DataFrame(), pd.DataFrame()
    monkeypatch.setattr(generator, 'build_demand', demand)
    previous_calls = []
    monkeypatch.setattr(previous_challenge, 'inject', lambda *args: previous_calls.append(True) or pd.DataFrame())
    actual_inject = challenge.inject
    new_calls = []
    def inject(*args):
        new_calls.append(True)
        return actual_inject(*args)
    monkeypatch.setattr(challenge, 'inject', inject)
    checked = []
    def dc(rng, days, stores, products, suppliers, orders):
        checked.append(True)
        expected = np.full_like(orders, 20)
        if seed == 92:
            _, _, _, nutrition, _, _, tags = generator.build_catalog(np.random.default_rng(seed))
            actual_inject(expected, days, stores, products, nutrition, tags)
            assert not np.array_equal(orders, np.full_like(orders, 20))
        np.testing.assert_array_equal(orders, expected)
        return orders.copy(), np.ones((len(days), len(products)), dtype=np.int64), pd.DataFrame()
    monkeypatch.setattr(generator, 'simulate_dc', dc)
    world = generator.generate(seed)
    assert checked and bool(previous_calls) == (seed == 91) and bool(new_calls) == (seed == 92)
    assert len(world.events) == (2 if seed == 92 else 0)


def test_scenario_public_description_is_generic():
    from scoop.demo_worlds import SCENARIOS
    scenario = next(s for s in SCENARIOS if s['seed'] == 92)
    assert scenario['name'] == 'New season' and scenario['default_week'] == '2026-07-27'
    assert not any(term in scenario['description'].lower() for term in ('kcal', 'sugar', 'premium', 'cup', 'hx92'))
