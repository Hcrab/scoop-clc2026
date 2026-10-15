"""Decision cards derived from fitted cohorts and computed purchase quantities."""
from math import sqrt
import numpy as np
from scipy.stats import norm


def cohort_name(leaf, groups):
    """Name the included scope; exclusions only qualify a positive parent."""
    priority = {'price_hkd':0, 'price_100ml':0, 'flavour':1, 'dairy':2, 'format':2}
    included = [step for step in leaf['tag_path'] if step['included']]
    product = [step for step in included if not step['id'].startswith('district:')]
    product.sort(key=lambda step:(priority.get(getattr(groups.get(step['id']), 'dimension', ''),3),step['id']))
    name = ' · '.join(getattr(groups.get(step['id']), 'name', step['id']).replace('Choc Coated','Chocolate-coated') for step in product)
    if any(not step['included'] for step in leaf['tag_path']):
        name = 'Other '+(name[0].lower()+name[1:] if name else 'products')
    if not name:
        name = ' · '.join(leaf['districts']) if included else 'Other products'
    elif any(step['id'].startswith('district:') for step in included):
        name += ' · '+', '.join(leaf['districts'])
    return name


def build_observations(result, cards, groups):
    """Project stored model leaves for the report without fitting or ordering again."""
    card_ids = {card['id'] for card in cards}
    observations = []
    for leaf in result.get('leaves', []):
        mean = leaf.get('posterior_mean',0.)
        low, high = leaf.get('interval_80',[mean,mean])
        observations.append({'id':leaf['id'], 'name':cohort_name(leaf,groups),
                             'tag_path':leaf['tag_path'], 'districts':leaf['districts'],
                             'skus':leaf['skus'], 'effect_pct':float(np.expm1(mean)*100),
                             'interval_pct':[float(np.expm1(low)*100),float(np.expm1(high)*100)],
                             'daily':leaf.get('daily',[]), 'in_card':leaf['id'] in card_ids,
                             'card_id':leaf['id'] if leaf['id'] in card_ids else None,
                             'method':{'leaf':leaf,'trace':result.get('method',{})}})
    return observations


def _shortage(mean, sigma, stock):
    if sigma <= 0:
        return max(0., mean-stock)
    z = (stock-mean)/sigma
    return sigma*norm.pdf(z)+(mean-stock)*norm.sf(z)


def _drilldown(leaf, groups):
    trace = leaf.get('drilldown')
    if trace is None:
        return None
    steps = []
    for step in trace['steps']:
        tag_id = step['tag_id']
        name = (tag_id.split(':', 1)[1] if tag_id.startswith('district:')
                else getattr(groups.get(tag_id), 'name', tag_id))
        label = name if step['included'] else 'Other ' + name[:1].lower() + name[1:]
        steps.append({**step, 'label': label})
    return {'root': {**trace['root'], 'label': 'All eligible products'}, 'steps': steps}


def build_cards(result, orders, baseline, products, groups, names):
    actual = orders.set_index('sku')
    plain = baseline.set_index('sku')
    catalog = products.set_index('sku')
    cards = []
    for leaf in result['leaves']:
        low, high = leaf['interval_80']
        if not any(step['included'] for step in leaf['tag_path']) or not leaf['split_p_values'] or not (low > 0 or high < 0):
            continue
        title = cohort_name(leaf, groups)
        skus = [s for s in leaf['skus'] if s in actual.index and s in plain.index]
        units = [u for u in result['units'] if u['leaf_id']==leaf['id']]
        shares = {}
        for sku in skus:
            total = sum(u.get('expected_recent',0) for u in result['units'] if u['sku']==sku)
            local = sum(u.get('expected_recent',0) for u in units if u['sku']==sku)
            shares[sku] = local/total if total else 0.
        delta_cases = 0.
        delta_pallets = 0.
        saved_margin = 0.
        per_sku = []
        for sku in skus:
            a, b, p = actual.loc[sku], plain.loc[sku], catalog.loc[sku]
            difference = int(a.final_cases-b.final_cases)
            sigma = max(0., float(a.demand_p90-a.demand_p10)/2.5632)
            saved = _shortage(float(a.demand_p50),sigma,float(a.inventory_position+b.final_cases*p.units_per_case)) - _shortage(float(a.demand_p50),sigma,float(a.inventory_position+a.final_cases*p.units_per_case))
            margin = saved * float(p.price_hkd-p.cost_hkd)
            delta_cases += difference * shares[sku]
            delta_pallets += difference * shares[sku]/float(p.cases_per_pallet)
            saved_margin += margin * shares[sku]
            per_sku.append({'sku':sku,'name':names.get(sku,sku), 'before_cases':int(b.final_cases),
                            'cases':int(a.final_cases), 'case_change':difference,
                            'district_forecast_share':shares[sku],
                            'expected_lost_margin_avoided':float(margin * shares[sku]),**result['sku_factors'][sku]})
        units = [u for u in result['units'] if u['leaf_id']==leaf['id']]
        excess = {s:sum(u.get('recent_A',0)-u.get('recent_E',0) for u in units if u['sku']==s) for s in skus}
        representative = min(skus, key=lambda s:(-excess[s], names.get(s,s))) if skus else None
        override_ids = [o['id'] for o in result.get('applied_overrides',[]) if any(u['sku'] in skus for u in o.get('matched_units',[])) or o.get('sku') in skus]
        cards.append({'id':leaf['id'],'name':title or ', '.join(leaf['districts']),
                      'tag_path':leaf['tag_path'],'districts':leaf['districts'],'skus':skus,
                      'effect_pct':float(np.expm1(leaf['posterior_mean'])*100),
                      'effect_basis':'Estimated sustained change in requested/forecast ratio from baseline to recent, after shrinkage; not the raw recent requested-minus-forecast percentage.',
                      'interval_pct':[float(np.expm1(low)*100),float(np.expm1(high)*100)],
                      'interval_coverage_pct':80.,'daily':leaf.get('daily',[]),'series_scope':leaf.get('series_scope',''),
                      'drilldown':_drilldown(leaf, groups),
                      'sku_factors':per_sku,'case_change':round(delta_cases),
                      'expected_lost_margin_avoided':float(saved_margin),'pallet_change':delta_pallets,
                      'pallet_change_basis':'Footprint of the change in total purchased cases; not a change in simultaneous warehouse peak occupancy.',
                      'peak_capacity':float(orders.projected_pallets.max()),
                      'peak_capacity_scope':'Whole warehouse with ALL cohort adjustments and current overrides already included together.',
                      'capacity_pallets':orders.attrs.get('capacity_pallets'),
                      'inherited_peak_pallets':orders.attrs.get('inherited_peak_pallets'),
                      'physical_capacity_excess_pallets':max(0.,float(orders.projected_pallets.max())-orders.attrs['capacity_pallets']) if orders.attrs.get('capacity_pallets') is not None else None,
                      'fits_physical_capacity':bool(orders.projected_pallets.max()<=orders.attrs['capacity_pallets']) if orders.attrs.get('capacity_pallets') is not None else None,
                      'representative_sku':representative,'override_ids':override_ids,
                      'method':{'leaf':leaf,'units':units,'trace':result['method'],
                                'order_impact_scope':'SKU order differences allocated by each leaf district forecast share; case total rounded. Disjoint district leaves do not duplicate total value.',
                                'value_method':'Normal expected shortage difference under the adjusted demand distribution'}})
    return sorted(cards,key=lambda c:(-c['expected_lost_margin_avoided'], -abs(c['case_change']), c['name']))
