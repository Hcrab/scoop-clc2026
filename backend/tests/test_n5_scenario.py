"""The illustrative compound world changes only its declared product/place cells."""
from datetime import timedelta

import numpy as np

from scoop.synth import compound_demo as scenario
from scoop.synth.generate import build_catalog
from scoop.synth.strawberry_challenge import cells


def test_seed93_compound_ramp_is_sustained_and_keeps_controls_unchanged():
    stores, _, products, _, _, _, tags = build_catalog(np.random.default_rng(93), seed=93)
    days = [scenario.START, scenario.START + timedelta(days=7), scenario.COATED_FULL,
            scenario.END, scenario.END + timedelta(days=1)]
    orders = np.full((len(days), len(stores), len(products)), 100, dtype=np.int64)
    events = scenario.inject(orders, days, stores, products, tags)
    target, _ = cells(products, tags)
    assert products.sku.iloc[target].tolist() == ['IC006', 'IC061', 'IC062', 'IC063']
    assert (orders[0] == 100).all() and (orders[-1] == 100).all()
    assert (orders[1, :, target] == 125).all()
    assert (orders[2:4, :, target] == 150).all()
    mango = products.sku.isin(tags.loc[tags.tag_id == 'flavour:mango', 'sku']).to_numpy()
    coated = products.sku.isin(tags.loc[tags.tag_id == 'feature:choc_coated', 'sku']).to_numpy()
    kowloon = stores.district.to_numpy() == 'Kowloon'
    assert (orders[2][np.ix_(kowloon, mango & ~coated)] == 135).all()
    assert (orders[2][np.ix_(~kowloon, mango & ~coated)] == 100).all()
    assert (orders[2, :, coated & ~mango] == 80).all()
    untouched = ~mango & ~coated & ~np.isin(np.arange(len(products)), target)
    assert (orders[:, :, untouched] == 100).all()
    assert set(events.id) == {'N5A', 'N5B', 'N5C', 'N5D'}
    assert min(scenario.HEATWAVE) > scenario.FULL
