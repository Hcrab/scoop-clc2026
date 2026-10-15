"""Private seed-93 illustrative interventions; never exposed as AI evidence."""
from datetime import date
import json

import numpy as np
import pandas as pd

from .strawberry_challenge import cells

START = date(2026, 7, 6)
FULL = date(2026, 7, 20)
END = date(2026, 8, 31)
STRAWBERRY_UPLIFT = .50
MANGO_KOWLOON_UPLIFT = .35
COATED_CHANGE = -.20
COATED_START = date(2026, 7, 20)
COATED_FULL = date(2026, 7, 27)
HEATWAVE = {date(2026, 7, 31): 33.6, **{
    date(2026, 8, day): temp for day, temp in
    [(1, 33.5), (2, 33.8), (3, 33.7), (4, 33.5), (5, 33.4),
     (6, 33.6), (7, 33.8), (8, 33.5)]}}


def inject(orders, days, stores, products, product_tags):
    """Round the same baseline draws after multiplying only the named cells."""
    strawberry, _ = cells(products, product_tags)
    mango = np.flatnonzero(products.sku.isin(product_tags.loc[
        product_tags.tag_id == 'flavour:mango', 'sku']).to_numpy())
    coated = np.flatnonzero(products.sku.isin(product_tags.loc[
        product_tags.tag_id == 'feature:choc_coated', 'sku']).to_numpy())
    kowloon = np.flatnonzero(stores.district.to_numpy() == 'Kowloon')
    for di, day in enumerate(days):
        if START < day <= END:
            ramp = min(1., (day - START).days / (FULL - START).days)
            orders[di, :, strawberry] = np.floor(
                orders[di, :, strawberry] * (1 + STRAWBERRY_UPLIFT * ramp) + .5)
            grid = np.ix_(kowloon, mango)
            orders[di][grid] = np.floor(
                orders[di][grid] * (1 + MANGO_KOWLOON_UPLIFT * ramp) + .5)
            coated_ramp = min(1., max(0., (day - COATED_START).days / (COATED_FULL - COATED_START).days))
            orders[di, :, coated] = np.floor(
                orders[di, :, coated] * (1 + COATED_CHANGE * coated_ramp) + .5)
    districts = sorted(stores.district.unique())
    rows = []
    for identifier, kind, tag, areas, skus, effect, start, full in [
        ('N5A', 'intersection', None, districts, products.sku.iloc[strawberry].tolist(), STRAWBERRY_UPLIFT, START, FULL),
        ('N5B', 'intersection', 'flavour:mango', ['Kowloon'], products.sku.iloc[mango].tolist(), MANGO_KOWLOON_UPLIFT, START, FULL),
        ('N5C', 'trend', 'feature:choc_coated', districts, products.sku.iloc[coated].tolist(), COATED_CHANGE, COATED_START, COATED_FULL),
    ]:
        rows.append(dict(id=identifier, kind=kind, tag_id=tag, sku=None,
                         districts=areas, start_date=start, end_date=END,
                         expected_label='persistent', note=json.dumps(dict(
                             skus=skus, peak_fraction=effect, full_effect_date=full.isoformat(),
                             ramp=f'linear for {(full-start).days} days, then sustained',
                             rounding='baseline draws multiplied, halves up; no new RNG draws'))))
    rows.append(dict(id='N5D', kind='heatwave', tag_id=None, sku=None,
                     districts=districts, start_date=min(HEATWAVE), end_date=max(HEATWAVE),
                     expected_label='weather', note='Illustrative 33.4–33.8C heat spike; issued forecasts use the ordinary lead-dependent noise.'))
    return pd.DataFrame(rows)
