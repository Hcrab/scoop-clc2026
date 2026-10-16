"""Couple seed93 draws to a heat episode wholly inside issued forecast skill."""
from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from scoop.synth import compound_demo as demo
from scoop.synth import generate as gen


def test_whole_episode_is_inside_issued_forecast_skill_at_same_intensity():
    assert min(demo.HEATWAVE) == date(2026, 7, 30)
    assert max(demo.HEATWAVE) == date(2026, 8, 2)
    assert (min(demo.HEATWAVE) - date(2026, 7, 27)).days == 3
    assert all(1 <= (day - date(2026, 7, 26)).days <= 7 for day in demo.HEATWAVE)
    assert np.mean(list(demo.HEATWAVE.values())) == pytest.approx(np.mean(list(demo.LEGACY_BASELINE_HEATWAVE.values())))
    assert min(demo.HEATWAVE.values()) == min(demo.LEGACY_BASELINE_HEATWAVE.values())
    assert max(demo.HEATWAVE.values()) == max(demo.LEGACY_BASELINE_HEATWAVE.values())


def test_shift_couples_units_forecasts_and_background_without_rng():
    days = gen._dates()
    rng = np.random.default_rng(93)
    weather, forecasts, _ = gen.build_weather(rng, days, heatwave=demo.LEGACY_BASELINE_HEATWAVE)
    background, _, _ = gen.build_weather(np.random.default_rng(93), days, heatwave={})
    np.testing.assert_array_equal(weather.attrs['background_tmax'], background.tmax)
    old_weather, old_forecasts = weather.copy(deep=True), forecasts.copy(deep=True)
    orders = np.full((len(days), 2, 3), 103, dtype=np.int64)
    old_orders = orders.copy()
    dairy = np.array([0., .45, 1.])
    state = deepcopy(rng.bit_generator.state)
    changes = demo.shift_heat_episode(weather, forecasts, orders, days, dairy=dairy,
                                      weather_total=.06, weather_pref=.045)
    assert rng.bit_generator.state == state
    for di, day in enumerate(days):
        delta = changes.get(day, 0.)
        expected = np.floor(old_orders[di] * np.exp((.06 + .045 * (.45 - dairy)) * delta) + .5)
        np.testing.assert_array_equal(orders[di], expected)
        if day in demo.HEATWAVE:
            assert weather.tmax.iloc[di] == demo.HEATWAVE[day]
        elif day in demo.LEGACY_BASELINE_HEATWAVE:
            assert weather.tmax.iloc[di] == weather.attrs['background_tmax'][di]
        else:
            pd.testing.assert_series_equal(weather.iloc[di], old_weather.iloc[di])
    delta = forecasts.target_date.map(changes).fillna(0.).to_numpy()
    lead = np.array([(target - issued).days for issued, target in
                     zip(forecasts.issued_date, forecasts.target_date)])
    weight = np.maximum(0., 1. - np.maximum(0, lead - 7) / 9.)
    np.testing.assert_array_equal(forecasts.tmax_fc, np.round(old_forecasts.tmax_fc + weight * delta, 1))
    pd.testing.assert_frame_equal(forecasts.drop(columns='tmax_fc'), old_forecasts.drop(columns='tmax_fc'))
    pd.testing.assert_series_equal(weather.rain_mm, old_weather.rain_mm)
    earlier = forecasts.target_date < min(demo.HEATWAVE)
    pd.testing.assert_frame_equal(forecasts[earlier], old_forecasts[earlier])
    assert np.all(weight[lead == 16] == 0.)
    assert any((forecasts.issued_date <= date(2026, 7, 27)) & (delta != 0) & (weight > 0))


@pytest.fixture(scope='module')
def paired_worlds():
    """Reusable comparison protocol: suppress only the deterministic shift."""
    snapshots = []
    actual_dc = gen.simulate_dc

    def dc(rng, *args):
        snapshots.append(deepcopy(rng.bit_generator.state))
        return actual_dc(rng, *args)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(gen, 'simulate_dc', dc)
        with pytest.MonkeyPatch.context() as baseline_patch:
            baseline_patch.setattr(demo, 'shift_heat_episode', lambda *args, **kwargs: {})
            baseline = gen.generate(93)
        shifted = gen.generate(93)
    return baseline, shifted, snapshots


def test_generation_preserves_history_opening_stock_pos_and_rng(paired_worlds):
    baseline, shifted, states = paired_worlds
    assert states[0] == states[1]
    first = min(demo.HEATWAVE)
    for name in ('store_orders', 'node_inventory', 'weather'):
        old, new = getattr(baseline, name), getattr(shifted, name)
        pd.testing.assert_frame_equal(old[old.date < first], new[new.date < first])
    old, new = baseline.purchase_orders, shifted.purchase_orders
    pd.testing.assert_frame_equal(old[old.order_date < first], new[new.order_date < first])
    for name in ('stores', 'suppliers', 'products', 'nutrition', 'tag_dimensions',
                 'tags', 'product_tags', 'promotions', 'nodes'):
        pd.testing.assert_frame_equal(getattr(baseline, name), getattr(shifted, name))
    dairy = shifted.product_tags.query("tag_id == 'dairy'").set_index('sku').value_num
    old = baseline.store_orders
    merged = old.merge(shifted.store_orders, on=['date', 'store_id', 'sku'], suffixes=('_old', '_new'))
    delta = merged.date.map(shifted.weather.set_index('date').tmax - baseline.weather.set_index('date').tmax)
    expected = np.floor(merged.ordered_units_old * np.exp(
        (.06 + .045 * (.45 - merged.sku.map(dairy))) * delta) + .5)
    np.testing.assert_array_equal(merged.ordered_units_new, expected)
    event = shifted.events.set_index('id').loc['N5D']
    assert (event.start_date, event.end_date) == (min(demo.HEATWAVE), max(demo.HEATWAVE))
    assert '30 July–2 August' in event.note
    assert (merged.ordered_units_old != merged.ordered_units_new).any()
    assert not baseline.node_inventory.equals(shifted.node_inventory)


def test_other_seeds_use_original_generation_path(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('heat shift called for a non93 seed')
    monkeypatch.setattr(demo, 'shift_heat_episode', unexpected)
    world = gen.generate(42)
    rng = np.random.default_rng(42)
    days = gen._dates()
    stores, suppliers, products, _, _, _, tags = gen.build_catalog(rng, seed=42)
    weather, forecasts, _ = gen.build_weather(rng, days)
    orders, _, _ = gen.build_demand(rng, days, stores, products, tags, weather)
    shipped, inventory, pos = gen.simulate_dc(rng, days, stores, products, suppliers, orders)
    pd.testing.assert_frame_equal(world.weather, weather)
    pd.testing.assert_frame_equal(world.forecasts, forecasts)
    pd.testing.assert_frame_equal(world.purchase_orders, pos)
    np.testing.assert_array_equal(world.store_orders.ordered_units, orders.reshape(-1))
    np.testing.assert_array_equal(world.store_orders.shipped_units, shipped.reshape(-1))
    np.testing.assert_array_equal(world.node_inventory.on_hand_units, inventory.reshape(-1))
