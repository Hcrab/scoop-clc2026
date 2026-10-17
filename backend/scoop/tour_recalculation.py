"""Derive tour annotations from recorded API snapshots, without recalculating plans."""
from math import isfinite


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError('Invalid tour recalculation number: ' + label)
    return value


def factor_inputs(snapshot, card_id, skus):
    model = snapshot['detail']['plan']['summary']['cohort_model']
    units = [u for u in model['units'] if u['leaf_id'] == card_id and u['sku'] in skus]
    rows = []
    for sku in skus:
        weight = sum(_number(u['expected_recent'], 'expected_recent') for u in units if u['sku'] == sku)
        if weight <= 0:
            raise ValueError('Missing positive expected-recent cohort weight: ' + sku)
        rows.append({'sku': sku, 'expected_recent': weight,
                     'f50': _number(model['sku_factors'][sku]['f50'], 'f50')})
    return rows


def cohort_factor(snapshot, card_id, skus):
    rows = factor_inputs(snapshot, card_id, skus)
    return sum(r['expected_recent'] * r['f50'] for r in rows) / sum(r['expected_recent'] for r in rows)


def recalculation(base, snapshot, card_id, skus):
    """Count only additional capacity cuts; context-driven demand changes are separate."""
    old_orders = {o['sku']: o for o in base['detail']['orders']}
    trimmed = []
    for order in sorted(snapshot['detail']['orders'], key=lambda o: o['sku']):
        before_cut = old_orders[order['sku']]['capacity_cut_cases']
        after_cut = order['capacity_cut_cases']
        if after_cut > before_cut:
            trimmed.append({'sku': order['sku'], 'name': order['name'],
                            'cases_trimmed': after_cut - before_cut,
                            'before_cut': before_cut, 'after_cut': after_cut})
    def cases(snap):
        return sum(o['effective_cases'] for o in snap['detail']['orders'] if o['sku'] in skus)
    return {'f_before': cohort_factor(base, card_id, skus),
            'f_after': cohort_factor(snapshot, card_id, skus),
            'before': cases(base), 'after': cases(snapshot),
            'p_before': _number(base['order_summary']['capacity']['projected_peak_pallets'], 'p_before'),
            'p_after': _number(snapshot['order_summary']['capacity']['projected_peak_pallets'], 'p_after'),
            'n': sum(r['cases_trimmed'] for r in trimmed), 'trimmed_products': trimmed}


def enrich_bundle(bundle, heat_temp):
    """Append v2 metadata in place; all recorded snapshots and answers stay untouched."""
    bundle['version'] = 2
    bundle['meta']['heat_temp'] = _number(heat_temp, 'heat_temp')
    for branch in bundle['branches'].values():
        branch['recalculation'] = recalculation(bundle['base'], branch['snapshot'],
                                              bundle['meta']['strawberry_card_id'],
                                              bundle['meta']['strawberry_skus'])
    return bundle


def heat_temperature(engine, heat_date):
    """Actual replay-day WeatherDaily tmax; never an issued weather forecast."""
    from sqlalchemy import text
    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            value = connection.execute(text('SELECT tmax FROM weather_daily WHERE date=:day'),
                                       {'day': heat_date}).scalar_one()
    return _number(value, 'WeatherDaily.tmax')
