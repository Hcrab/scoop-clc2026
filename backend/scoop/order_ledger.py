"""Plain-word, arithmetical presentation of saved replenishment decisions.

This reads decisions; it never changes targets, quantities or ordering policy.
"""
from decimal import Decimal, ROUND_HALF_UP
from math import ceil, isclose


def whole(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def order_ledger(order, summary=None):
    summary = summary or {}
    forecast = float(order['demand_p50'])
    target = float(order['target_units'])
    stock, transit = int(order['on_hand_units']), int(order['on_order_units'])
    pack = int(order['units_per_case'])
    forecast_units, safety_units = whole(forecast), whole(target - forecast)
    # Integer inventory and pack sizes make ceil(target) give exactly the same
    # case ceiling as the unrounded algorithm. Keep independent safety rounding
    # visible instead of silently moving a residual into the safety buffer.
    target_units = ceil(target)
    net_units = target_units - stock - transit
    need_units = max(0, net_units)
    packed_cases = ceil(need_units / pack) if need_units else 0
    suggested = int(order['suggested_cases'])
    cut = int(order['capacity_cut_cases'])
    calculated = max(0, suggested - cut)
    final = order.get('final_cases')
    effective = int(final) if final is not None else calculated
    replaced = final is not None and effective != calculated
    minimum = int(order.get('moq_cases', 0))
    # A final quantity replaces the calculated recommendation. In particular,
    # an edited zero is not an order raised to the supplier minimum or trimmed
    # by the old capacity calculation.
    minimum_added = (minimum - packed_cases if not replaced and 0 < packed_cases < minimum
                     and suggested == minimum else 0)
    applied_cut = cut if not replaced else 0
    case_adjustment = effective - (packed_cases + minimum_added - applied_cut)

    # Notes name the plan's presented groups, not every fitted remainder leaf.
    # Tiny background factors remain in the forecast without claiming that an
    # unrelated product belongs to the named trend.
    cards = [card for card in summary.get('cohort_cards', []) if order['sku'] in card.get('skus', [])]
    trend = None
    factor = float(order.get('adjustment', 1))
    if cards and not isclose(factor, 1., abs_tol=1e-9):
        trend = {'percent': (factor - 1) * 100,
                 'name': ' / '.join(card['name'] for card in cards) or 'this product group'}

    return {
        'days': int(order['protection_days']), 'in_stock_target_percent': float(order['critical_ratio']) * 100,
        'forecast_units': forecast_units, 'safety_units': safety_units,
        'rounding_units': target_units - forecast_units - safety_units,
        'target_units': target_units, 'stock_units': stock, 'transit_units': transit,
        'net_units': net_units, 'need_units': need_units, 'surplus_units': max(0, -net_units),
        'units_per_case': pack, 'packed_cases': packed_cases,
        'minimum_added_cases': minimum_added, 'capacity_removed_cases': applied_cut,
        'case_adjustment': case_adjustment, 'quantity_edited': replaced,
        'effective_cases': effective, 'trend': trend,
    }


def present_order(order, summary=None):
    ledger = order_ledger(order, summary)
    # Replace the concrete algorithm presenter, including the CSV reason. Saved
    # free-form AI replies are deliberately not inspected or rewritten.
    reason = (f"{ledger['need_units']:,} units still needed over {ledger['days']} days; "
              f"{ledger['effective_cases']:,} cases of {ledger['units_per_case']} units.")
    return {**order, 'effective_cases': ledger['effective_cases'], 'ledger': ledger, 'reason': reason}
