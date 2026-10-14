"""Private seed 93 intervention and offline evaluation metadata."""
from datetime import date, timedelta
from itertools import combinations
import json

import numpy as np
import pandas as pd

SEED = 93
START = date(2026, 7, 6)
FULL = date(2026, 7, 13)
END = date(2026, 8, 31)
PEAK = .80
GROUP_IDS = ('flavour:strawberry', 'band:dairy:0', 'band:price_hkd:0')


def cells(products, product_tags):
    """Use the public catalog's existing water/unit-price tercile definitions."""
    parents = {}
    parents[GROUP_IDS[0]] = products.sku.isin(
        product_tags.loc[product_tags.tag_id == GROUP_IDS[0], 'sku']
    ).to_numpy()
    for dim, identifier in [('dairy', GROUP_IDS[1]), ('price_hkd', GROUP_IDS[2])]:
        values = product_tags.loc[product_tags.tag_id == dim].set_index('sku').loc[products.sku, 'value_num'].to_numpy()
        parents[identifier] = np.digitize(values, np.quantile(values, [1/3, 2/3]), right=True) == 0
    target = np.logical_and.reduce(list(parents.values()))
    return np.flatnonzero(target), parents


def answer_key(products, product_tags, stores):
    """Private dates, memberships, effects and controls for offline scoring."""
    indices, parents = cells(products, product_tags)
    if len(indices) < 3 or products.iloc[indices].size_ml.nunique() != 1:
        raise ValueError('The intervention requires three or more equal-size single servings.')
    target = np.zeros(len(products), dtype=bool)
    target[indices] = True
    controls = []
    for count in (1, 2):
        for ids in combinations(GROUP_IDS, count):
            mask = np.logical_and.reduce([parents[identifier] for identifier in ids]) & ~target
            controls.append(dict(group_ids=list(ids), skus=products.sku.loc[mask].tolist()))
    return dict(
        id='HX93A', group_ids=list(GROUP_IDS), skus=products.sku.iloc[indices].tolist(),
        districts=sorted(stores.district.unique()), store_ids=stores.id.tolist(),
        start_date=START.isoformat(), full_effect_date=FULL.isoformat(), end_date=END.isoformat(),
        effect=dict(peak_fraction=PEAK, ramp='linear, sustained after full effect',
                    units_rule='Round baseline requested units times multiplier, halves up; no RNG draws.'),
        controls=dict(parent_and_pair_remainders=controls,
                      unaffected_skus=products.sku.loc[~target].tolist(),
                      pre_intervention_end=(START-timedelta(days=1)).isoformat()),
    )


def inject(orders, days, stores, products, product_tags):
    """Apply one sustained request uplift before DC shipments and replenishment."""
    if orders.shape != (len(days), len(stores), len(products)):
        raise ValueError('Order cube does not match the catalog and calendar.')
    if not np.issubdtype(orders.dtype, np.integer) or np.any(orders < 0):
        raise ValueError('Demand must contain nonnegative integer units.')
    key = answer_key(products, product_tags, stores)
    indices, _ = cells(products, product_tags)
    for di, day in enumerate(days):
        if START < day <= END:
            multiplier = 1 + PEAK * min(1., (day-START).days / (FULL-START).days)
            orders[di, :, indices] = np.floor(orders[di, :, indices] * multiplier + .5).astype(orders.dtype)
    return pd.DataFrame([dict(id=key['id'], kind='intersection', tag_id=None, sku=None,
                              districts=key['districts'], start_date=START, end_date=END,
                              expected_label='persistent', note=json.dumps(key, sort_keys=True))])
