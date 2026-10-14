"""Offline cohort evaluation frames built from one internally consistent world."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scoop.algorithms.forecast import Static
from scoop.algorithms.groups import BANDED, MIN_SKUS, TAG_DIMENSIONS
from scoop.synth import generate as synth


@dataclass
class EvalWorld:
    static: Static
    groups: dict[str, set[str]]
    stores: dict[str, str]
    skus: list[str]
    orders: pd.DataFrame
    promotions: list
    weather: pd.DataFrame


def make_world(seed: int, *, planted: bool = False) -> EvalWorld:
    """Replay generator RNG through demand; no DB state or other seed is consulted."""
    rng = np.random.default_rng(seed)
    days = synth._dates()
    stores, suppliers, products, nutrition, _, tags, product_tags = synth.build_catalog(rng, seed=seed)
    weather, forecasts, _ = synth.build_weather(rng, days)
    cube, promotions, _ = synth.build_demand(rng, days, stores, products, product_tags, weather, planted=planted)
    if planted and seed == 93:
        from scoop.synth.strawberry_challenge import inject
        inject(cube, days, stores, products, product_tags)
    idx = pd.MultiIndex.from_product([days, stores.id, products.sku], names=['date', 'store_id', 'sku'])
    orders = pd.DataFrame({'ordered_units': cube.reshape(-1)}, index=idx).reset_index()
    orders['date'] = pd.to_datetime(orders.date)

    features = products.merge(suppliers[['id', 'lead_time_days', 'order_weekday', 'review_days']],
                              left_on='supplier_id', right_on='id').drop(columns=['id'])
    values = product_tags.pivot_table(index='sku', columns='tag_id', values='value_num', aggfunc='max')
    for col in ('dairy', 'richness', 'sweetness', 'sugar_100ml'):
        features[col] = features.sku.map(values[col])
    for col, tag in (('choc_coated', 'feature:choc_coated'), ('low_sugar', 'health:low_sugar')):
        features[col] = features.sku.map(values[tag]).fillna(0).astype(int)
    family = product_tags[product_tags.tag_id.str.startswith('family:')].set_index('sku').tag_id.str.split(':').str[1]
    features['family'] = features.sku.map(family)
    weather['date'] = pd.to_datetime(weather.date)
    forecasts['issued_date'] = pd.to_datetime(forecasts.issued_date)
    forecasts['target_date'] = pd.to_datetime(forecasts.target_date)
    climate = weather.groupby(weather.date.dt.dayofyear).tmax.mean().rolling(15, center=True, min_periods=1).mean()
    static = Static(stores.rename(columns={'id': 'store_id'})[['store_id', 'district', 'size_factor']],
                    features, promotions[['sku', 'start_date', 'end_date', 'discount_pct']], weather, forecasts, climate)

    groups = {}
    joined = product_tags.merge(tags[['id', 'dimension_id']], left_on='tag_id', right_on='id')
    for dim in TAG_DIMENSIONS:
        for tag_id, part in joined[joined.dimension_id == dim].groupby('tag_id'):
            if part.sku.nunique() >= MIN_SKUS:
                groups[tag_id] = set(part.sku)
    for dim in BANDED:
        sub = product_tags[product_tags.tag_id == dim].set_index('sku').value_num
        band = np.digitize(sub.to_numpy(), np.quantile(sub.to_numpy(), [1/3, 2/3]), right=True)
        for b in range(3):
            members = set(sub.index[band == b])
            if len(members) >= MIN_SKUS:
                groups[f'band:{dim}:{b}'] = members
    price = np.round(products.price_hkd.to_numpy() / products.size_ml.to_numpy() * 100, 2)
    kcal = nutrition.kcal.to_numpy() / nutrition.serving_ml.to_numpy() * 100
    for dim, vals, sku_values in (('price_100ml', price, products.sku), ('kcal_100ml', kcal, nutrition.sku)):
        band = np.digitize(vals, np.quantile(vals, [1/3, 2/3]), right=True)
        for b in range(3):
            members = set(sku_values[band == b])
            if len(members) >= MIN_SKUS:
                groups[f'band:{dim}:{b}'] = members
    return EvalWorld(static, groups, dict(zip(stores.id, stores.district)), sorted(products.sku),
                     orders, list(promotions.itertuples(index=False)), weather)


def save_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
