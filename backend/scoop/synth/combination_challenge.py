"""Private seed92 demand interventions; never imported by operational read tools."""
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd

SEED = 92
DEFAULT_WEEK = '2026-07-27'
END = date(2026, 8, 31)


def cells(products, nutrition, product_tags):
    """Catalog terciles use the same quantile/digitize rule as algorithms.groups."""
    label = nutrition.set_index('sku').loc[products.sku]
    kcal = (label.kcal / label.serving_ml * 100).to_numpy()
    numeric = {}
    for dim in ('price_hkd', 'sugar_100ml'):
        numeric[dim] = product_tags.loc[product_tags.tag_id == dim].set_index('sku').loc[products.sku, 'value_num'].to_numpy()
    numeric['kcal_100ml'] = kcal
    edges = {dim: np.quantile(values, [1 / 3, 2 / 3]) for dim, values in numeric.items()}
    bands = {dim: np.digitize(values, edges[dim], right=True) for dim, values in numeric.items()}
    parents = {
        'lower_kcal': bands['kcal_100ml'] == 0,
        'premium_price': bands['price_hkd'] == 2,
        'lower_sugar': bands['sugar_100ml'] == 0,
        'cup': products['format'].to_numpy() == 'cup',
    }
    groups = {
        'lower_kcal_premium': np.flatnonzero(parents['lower_kcal'] & parents['premium_price']),
        'lower_sugar_cup': np.flatnonzero(parents['lower_sugar'] & parents['cup']),
    }
    return groups, parents, edges


def answer_key(products, nutrition, product_tags, stores):
    """Offline evaluator metadata, stored only in ground_truth_events notes."""
    groups, parents, edges = cells(products, nutrition, product_tags)
    if any(len(indices) < 3 for indices in groups.values()):
        raise ValueError('Combination challenge requires at least three SKUs in each intersection.')
    relationships = []
    for identifier, name, axes, districts, start, full, peak in [
        ('HX92A', 'lower_kcal_premium', ('lower_kcal', 'premium_price'), ['Kowloon', 'HK Island'], date(2026, 7, 6), date(2026, 7, 13), .65),
        ('HX92B', 'lower_sugar_cup', ('lower_sugar', 'cup'), ['NT East', 'NT West'], date(2026, 7, 13), date(2026, 7, 20), .55),
    ]:
        members = products.sku.iloc[groups[name]].tolist()
        mask = np.zeros(len(products), dtype=bool)
        mask[groups[name]] = True
        relationships.append(dict(
            id=identifier, combination=name, skus=members, districts=districts,
            store_ids=stores.loc[stores.district.isin(districts), 'id'].tolist(),
            start_date=start.isoformat(), full_effect_date=full.isoformat(), end_date=END.isoformat(),
            effect=dict(peak_fraction=peak, ramp='linear, sustained after full effect', units_rule='Round baseline ordered units times multiplier to nearest integer, halves up; no RNG draws.'),
            dimensions=axes, tercile_edges={dim: values.tolist() for dim, values in edges.items()},
            negative_controls=dict(
                same_skus_other_districts=dict(skus=members, districts=sorted(set(stores.district) - set(districts))),
                parent_only={axis: products.sku.loc[parents[axis] & ~mask].tolist() for axis in axes},
                pre_intervention_end=(start - timedelta(days=1)).isoformat(),
            ),
        ))
    return dict(seed=SEED, default_week=DEFAULT_WEEK, relationships=relationships)


def inject(orders, days, stores, products, nutrition, product_tags):
    """Mutate only target intersection demand before shipments and DC replenishment."""
    if orders.shape != (len(days), len(stores), len(products)):
        raise ValueError('Order cube does not match the catalog and calendar.')
    if not np.issubdtype(orders.dtype, np.integer) or np.any(orders < 0):
        raise ValueError('Demand must contain nonnegative integer units.')
    key = answer_key(products, nutrition, product_tags, stores)
    groups, _, _ = cells(products, nutrition, product_tags)
    events = []
    for relationship in key['relationships']:
        start = date.fromisoformat(relationship['start_date'])
        full = date.fromisoformat(relationship['full_effect_date'])
        peak = relationship['effect']['peak_fraction']
        store_indices = np.flatnonzero(stores.district.isin(relationship['districts']).to_numpy())
        sku_indices = groups[relationship['combination']]
        for di, day in enumerate(days):
            if day <= start or day > END:
                continue
            multiplier = 1 + peak * min(1., (day - start).days / (full - start).days)
            index = np.ix_([di], store_indices, sku_indices)
            orders[index] = np.floor(orders[index] * multiplier + .5).astype(orders.dtype)
        events.append(dict(id=relationship['id'], kind='intersection', tag_id=None, sku=None,
                           districts=relationship['districts'], start_date=start, end_date=END,
                           expected_label='persistent', note=json.dumps(relationship, sort_keys=True)))
    return pd.DataFrame(events)
