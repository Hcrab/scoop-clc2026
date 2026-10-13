"""Read-only temperature scenarios using the same purchasing code as the plan."""
from datetime import timedelta
from sqlalchemy import select
from ..models import DirectionItem


def temperature_scenario(session, plan, temperature_c: float, offset_days: int = 7):
    from ..planning import suggest_orders
    if not 15 <= temperature_c <= 45 or offset_days not in (0, 7):
        raise ValueError('Choose 15-45 C and this week or next week')
    start = plan.week_start + timedelta(days=offset_days)
    end = start + timedelta(days=6)
    directions = [dict(bucket=d.bucket, tag_id=d.tag_id, sku=d.sku, districts=d.districts, factor=d.factor)
                  for d in session.scalars(select(DirectionItem).where(DirectionItem.plan_id == plan.id))]
    kwargs = dict(service_level=plan.service_level, goal=plan.goal)
    base = suggest_orders(plan.week_start, directions, **kwargs)
    changed = suggest_orders(plan.week_start, directions, weather_scenario=(start,end,float(temperature_c)), **kwargs)
    b = base.set_index('sku'); c = changed.set_index('sku')
    differences = (c.final_cases - b.final_cases).sort_values(key=abs, ascending=False)
    return {
        'start_date': start.isoformat(), 'end_date': end.isoformat(), 'temperature_c': temperature_c,
        'baseline_cases': int(b.final_cases.sum()), 'scenario_cases': int(c.final_cases.sum()),
        'delta_cases': int(c.final_cases.sum()-b.final_cases.sum()),
        'baseline_p50_units': float(b.demand_p50.sum()), 'scenario_p50_units': float(c.demand_p50.sum()),
        'changed_skus': [{'sku':sku,'baseline_cases':int(b.loc[sku,'final_cases']),
                          'scenario_cases':int(c.loc[sku,'final_cases']),'delta_cases':int(delta)}
                         for sku,delta in differences.items() if delta != 0],
        'applied': False,
        'assumptions': 'Only the stated seven-day maximum-temperature forecast changes. Rain, directions, inventory, objective and supplier dates stay fixed. Quantities cover each SKU protection interval.',
        'limitation': 'Tree models have limited extrapolation beyond training temperatures. This is a model sensitivity calculation, not a validated extreme-heat prediction or an applied order.',
    }
