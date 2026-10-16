"""Plan-owned dashboard widgets backed by observed history."""
from datetime import timedelta
from math import isfinite
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func

from .models import Product, Supplier, Node, Store, StoreOrder, NodeInventory, WatchItem, DailyExpectation, ModelRun, PurchaseOrder, PurchaseSuggestion
from .ai.exploration_tools import _groups

METRICS = {'on_hand', 'lost_units', 'demand', 'fill_rate', 'days_cover', 'lowest_cover',
           'pallets', 'requested_vs_expected'}
UNITS = {'on_hand': 'units', 'lost_units': 'units', 'demand': 'units',
         'fill_rate': 'ratio', 'days_cover': 'days', 'pallets': 'pallets',
          'requested_vs_expected': 'units', 'lowest_cover': 'days'}


def options(session, plan):
    result = [{'kind': 'warehouse', 'key': '', 'label': 'Whole warehouse'}]
    seen = {('warehouse', '')}
    for card in (plan.summary or {}).get('cohort_cards', []):
        key = ('cohort', card['id'])
        if key not in seen:
            result.append({'kind': key[0], 'key': key[1], 'label': card.get('name') or key[1]})
            seen.add(key)
    for group in _groups(session).values():
        key = ('tag', group.id)
        if key not in seen:
            result.append({'kind': key[0], 'key': key[1], 'label': group.name})
            seen.add(key)
    products = list(session.scalars(select(Product).order_by(Product.sku)))
    for brand in sorted({p.brand for p in products}):
        result.append({'kind': 'brand', 'key': brand, 'label': brand})
    for product in products:
        result.append({'kind': 'sku', 'key': product.sku, 'label': product.name})
    return result


def canonical(spec):
    """Reject malformed IDs and non-finite thresholds before persistence."""
    title = spec.get('title')
    scope = spec.get('scope')
    metric = spec.get('metric')
    threshold = spec.get('threshold')
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise HTTPException(422, 'Widget title must be 1–160 characters')
    if not isinstance(scope, dict) or set(scope) - {'kind', 'key'} or scope.get('kind') not in {'warehouse', 'cohort', 'tag', 'brand', 'sku'}:
        raise HTTPException(422, 'Choose a dashboard scope')
    kind, key = scope['kind'], scope.get('key', '')
    if not isinstance(key, str) or (kind != 'warehouse' and not key) or (kind == 'warehouse' and key):
        raise HTTPException(422, 'Choose a valid scope key')
    if metric not in METRICS:
        raise HTTPException(422, 'Choose a dashboard metric')
    if threshold is not None:
        if not isinstance(threshold, dict) or set(threshold) != {'operator', 'value'} or threshold['operator'] not in {'lt', 'gt'} or type(threshold['value']) not in (int, float) or not isfinite(threshold['value']):
            raise HTTPException(422, 'Choose a finite threshold and lt/gt operator')
        threshold = {'operator': threshold['operator'], 'value': float(threshold['value'])}
    return {'title': title.strip(), 'scope': {'kind': kind, 'key': key},
            'metric': metric, 'threshold': threshold}


def resolve(session, plan, spec):
    kind, key = spec['scope']['kind'], spec['scope']['key']
    products = {p.sku: p for p in session.scalars(select(Product))}
    if kind == 'warehouse': return sorted(products)
    if kind == 'sku':
        if key not in products: raise HTTPException(422, 'Unknown SKU')
        return [key]
    if kind == 'brand':
        selected = sorted(p.sku for p in products.values() if p.brand == key)
        if not selected: raise HTTPException(422, 'Unknown brand')
        return selected
    if kind == 'tag':
        group = _groups(session).get(key)
        if group is None: raise HTTPException(422, 'Unknown catalog group')
        selected = sorted(set(group.skus) & set(products))
        if not selected: raise HTTPException(422, 'Catalog group has no products')
        return selected
    card = next((c for c in (plan.summary or {}).get('cohort_cards', []) if c['id'] == key), None)
    if card is None: raise HTTPException(422, 'Unknown plan cohort')
    selected = sorted(set(card.get('skus', [])) & set(products))
    if not selected: raise HTTPException(422, 'Plan cohort has no products')
    return selected


def active(session, plan):
    return [w for w in session.scalars(select(WatchItem).where(WatchItem.plan_id == plan.id, WatchItem.status == 'active')) if isinstance(w.scope, dict) and 'metric' in w.scope]


def ordered(session, plan):
    items = active(session, plan)
    positions = {wid: i for i, wid in enumerate((plan.summary or {}).get('dashboard_order', []))}
    return sorted(items, key=lambda w: (positions.get(w.id, len(positions)), w.id))


def initialize(session, plan):
    # Called only from a mutation. A read must never write layout or widgets.
    if 'dashboard_order' not in (plan.summary or {}):
        plan.summary = {**(plan.summary or {}), 'dashboard_order': [w.id for w in ordered(session, plan)]}


def seed_defaults(session, plan):
    """Draft the initial measures once, as part of explicit plan creation."""
    if 'dashboard_order' in (plan.summary or {}):return
    existing=ordered(session,plan)
    if existing:
        initialize(session,plan)
        return
    specs=[{'title':f"{card['name']} stock",'scope':{'kind':'cohort','key':card['id']},
            'metric':'on_hand','threshold':None}
           for card in (plan.summary or {}).get('cohort_cards',[])[:2]]
    if not specs:
        specs.append({'title':'Warehouse stock','scope':{'kind':'warehouse'},'metric':'on_hand','threshold':None})
    specs.extend({'title':title,'scope':{'kind':'warehouse'},'metric':metric,'threshold':None}
                 for title,metric in [('Cold-store use','pallets'),('Lowest days of cover','lowest_cover')])
    ids=[save(session,plan,spec,origin='baseline').id for spec in specs]
    plan.summary={**(plan.summary or {}),'dashboard_order':ids}
    session.flush()


def apply_report_defaults(session, plan, report):
    """Use the analyst's widget selection while the layout is still untouched."""
    specs = report.get('dashboard_widgets')
    if not specs or (plan.summary or {}).get('dashboard_customized'):
        return False
    current = ordered(session, plan)
    # An intentionally empty layout or user-added widget belongs to the planner.
    if not current or any(widget.origin != 'baseline' for widget in current):
        return False
    canonical_specs = [canonical(spec) for spec in specs]
    for spec in canonical_specs:
        resolve(session, plan, spec)
    for widget in current:
        session.delete(widget)
    session.flush()
    ids = [save(session, plan, spec, origin='baseline').id for spec in canonical_specs]
    plan.summary = {**(plan.summary or {}), 'dashboard_order': ids,
                    'dashboard_default_source': 'ai'}
    session.flush()
    return True


def save(session, plan, spec, origin='decision'):
    spec = canonical(spec)
    resolve(session, plan, spec)
    # Unique(plan_id,title) includes archived legacy items.
    existing = session.scalar(select(WatchItem).where(WatchItem.plan_id == plan.id, WatchItem.title == spec['title']))
    if existing: raise HTTPException(422, 'Widget title already exists')
    widget = WatchItem(id=uuid4().hex, plan_id=plan.id, kind='req_vs_expected' if spec['metric'] == 'requested_vs_expected' else spec['metric'], title=spec['title'],
                       assumption='', scope=spec, origin=origin, status='active')
    session.add(widget)
    session.flush()
    return widget


def historical_facts(session, plan, need_expected=False):
    """Aggregate the fixed history window once for every widget in a response."""
    end = plan.week_start
    start = end - timedelta(days=28)
    warmup = start - timedelta(days=7)
    products = {p.sku: p for p in session.scalars(select(Product))}
    store_count = session.scalar(select(func.count()).select_from(Store)) or 0
    orders = {}
    for day, sku, demand, shipped, count in session.execute(
        select(StoreOrder.date, StoreOrder.sku, func.sum(StoreOrder.ordered_units),
               func.sum(StoreOrder.shipped_units), func.count(StoreOrder.store_id))
        .where(StoreOrder.date >= warmup, StoreOrder.date < end)
        .group_by(StoreOrder.date, StoreOrder.sku)):
        orders[(day, sku)] = (float(demand), float(shipped)) if count == store_count else None
    stock = {(day, sku): float(units) for day, sku, units in session.execute(
        select(NodeInventory.date, NodeInventory.sku, NodeInventory.on_hand_units)
        .where(NodeInventory.date >= start, NodeInventory.date < end))}
    runs = list(session.scalars(select(ModelRun).where(ModelRun.trained_through < end)
                                .order_by(ModelRun.trained_through.desc(), ModelRun.created_at.desc()))) if need_expected else []
    run_for_day = {}
    day = start
    while day < end:
        run_for_day[day] = next((run for run in runs if run.trained_through < day), None)
        day += timedelta(days=1)
    selected_run_ids = {run.id for run in run_for_day.values() if run is not None}
    issued = {}
    if selected_run_ids:
        for run_id, day, sku, value, count in session.execute(
            select(DailyExpectation.run_id, DailyExpectation.date, DailyExpectation.sku,
                   func.sum(DailyExpectation.p50), func.count(DailyExpectation.store_id))
            .where(DailyExpectation.run_id.in_(selected_run_ids),
                   DailyExpectation.date >= start, DailyExpectation.date < end)
            .group_by(DailyExpectation.run_id, DailyExpectation.date, DailyExpectation.sku)):
            issued[(run_id, day, sku)] = float(value) if count == store_count else None
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}
    capacity = session.scalar(select(Node.capacity_pallets).where(Node.id == 'DC1')) or 0
    arrivals = {}
    def add_arrival(sku, day, units):
        if day >= end and units > 0:
            arrivals.setdefault(sku, {}).setdefault(day, 0)
            arrivals[sku][day] += units
    # Only promises already known at the order boundary. An overdue unresolved
    # shipment has no new promised date; future recorded receipt facts stay hidden.
    for order in session.scalars(select(PurchaseOrder).where(
            PurchaseOrder.source == 'history', PurchaseOrder.order_date < end)):
        if order.received_date is None or order.received_date >= end:
            add_arrival(order.sku, order.expected_date,
                        order.cases * products[order.sku].units_per_case)
    for order in session.scalars(select(PurchaseSuggestion).where(
            PurchaseSuggestion.plan_id == plan.id)):
        cases = order.final_cases if order.final_cases is not None else max(0, order.suggested_cases - order.capacity_cut_cases)
        if end <= order.order_date < end + timedelta(days=7):
            product = products[order.sku]
            add_arrival(order.sku, order.order_date + timedelta(days=suppliers[product.supplier_id].lead_time_days),
                        cases * product.units_per_case)
    return {'orders': orders, 'stock': stock, 'issued': issued, 'runs': run_for_day,
            'products': products, 'suppliers': suppliers, 'capacity': capacity,
            'start': start, 'end': end, 'arrivals': arrivals}


def _total(facts, day, skus, source):
    values = [facts[source].get((day, sku)) for sku in skus]
    return sum(values) if values and all(value is not None for value in values) else None


def _demand(facts, day, skus, field=0):
    rows = [facts['orders'].get((day, sku)) for sku in skus]
    return sum(row[field] for row in rows) if rows and all(row is not None for row in rows) else None


def _average_demand(facts, day, skus):
    preceding = [_demand(facts, day - timedelta(days=i), skus) for i in range(1, 8)]
    return sum(preceding) / 7 if all(value is not None for value in preceding) else None


def health_snapshot(facts):
    """Fixed warehouse health, independent of editable widget selection."""
    end, history_start = facts['end'], facts['start']
    start = end - timedelta(days=14)
    through = end - timedelta(days=1)
    requested = shipped = sku_days = 0
    ran_out = set()
    for (day, sku), row in facts['orders'].items():
        if start <= day < end and row is not None:
            requested += row[0]
            shipped += row[1]
            if row[0] > row[1]:
                sku_days += 1
                ran_out.add(sku)
    products = []
    pallets = {}
    for sku, product in sorted(facts['products'].items()):
        recent = [_demand(facts, end - timedelta(days=i), [sku]) for i in range(7, 0, -1)]
        average = sum(recent) / 7 if all(value is not None for value in recent) else None
        stock = facts['stock'].get((through, sku))
        supplier = facts['suppliers'][product.supplier_id]
        arrivals = [{'date': day.isoformat(), 'units': units}
                    for day, units in sorted(facts.get('arrivals', {}).get(sku, {}).items())]
        next_date = arrivals[0]['date'] if arrivals else None
        products.append({'sku': sku, 'name': product.name,
                         'on_hand_units': stock if stock is not None else 0,
                         'daily_demand': average,
                         'days_cover': stock / average if stock is not None and average and average > 0 else None,
                         'lead_time_days': supplier.lead_time_days, 'recent_demand': recent,
                         'next_arrivals': arrivals, 'next_arrival_date': next_date,
                         'days_until_arrival': (min(facts['arrivals'][sku]) - end).days if arrivals else None})
        footprint = product.units_per_case * product.cases_per_pallet
        for (day, stock_sku), units in facts['stock'].items():
            if stock_sku == sku:
                pallets[day] = pallets.get(day, 0) + units / footprint
    history = []
    skus = list(facts['products'])
    day = history_start
    while day < end:
        demand = _demand(facts, day, skus)
        fulfilled = _demand(facts, day, skus, 1)
        stock = _total(facts, day, skus, 'stock')
        history.append({'date': day.isoformat(), 'requested_units': demand,
                        'shipped_units': fulfilled,
                        'lost_units': demand - fulfilled if demand is not None and fulfilled is not None else None,
                        'on_hand_units': stock,
                        'pallets': pallets.get(day) if stock is not None else None})
        day += timedelta(days=1)
    return {'period_start': start.isoformat(), 'through': through.isoformat(),
            'requested_units': requested, 'shipped_units': shipped,
            'fill_rate': shipped / requested if requested else 1,
            'stockout_skus': sorted(ran_out), 'stockout_sku_days': sku_days,
            'pallets': pallets.get(through, 0), 'peak_pallets': max((value for day, value in pallets.items() if start <= day < end), default=0),
            'capacity_pallets': facts['capacity'], 'products': products, 'history': history}


def representative_sku(plan, spec, skus, products):
    """Choose an illustration from saved plan evidence without recalculating it."""
    if spec['scope']['kind'] == 'sku':
        return skus[0]
    summary = plan.summary or {}
    if spec['scope']['kind'] == 'cohort':
        card = next((card for card in summary.get('cohort_cards', [])
                     if card['id'] == spec['scope']['key']), None)
        if card and card.get('representative_sku') in skus:
            return card['representative_sku']
    excess = {}
    for unit in summary.get('cohort_model', {}).get('units', []):
        sku = unit['sku']
        if sku in skus:
            excess[sku] = excess.get(sku, 0) + unit.get('recent_A', 0) - unit.get('recent_E', 0)
    candidates = excess if excess else skus
    return min(candidates, key=lambda sku: (-excess.get(sku, 0), products[sku].name, sku)) if candidates else None


def evaluate(session, plan, spec, widget_id='preview', facts=None):
    spec = canonical(spec)
    skus = resolve(session, plan, spec)
    facts = facts or historical_facts(session, plan, spec['metric'] == 'requested_vs_expected')
    start, end = facts['start'], facts['end']
    series = []
    threshold = spec['threshold']
    day = start
    while day < end:
        value = None
        metric = spec['metric']
        demand = _demand(facts, day, skus)
        shipped = _demand(facts, day, skus, 1)
        on_hand = _total(facts, day, skus, 'stock')
        if metric in {'demand', 'requested_vs_expected'}: value = demand
        elif metric == 'lost_units' and demand is not None and shipped is not None: value = demand - shipped
        elif metric == 'fill_rate' and demand: value = shipped / demand
        elif metric == 'on_hand': value = on_hand
        elif metric == 'pallets' and on_hand is not None:
            value = sum(facts['stock'][(day, sku)] / (facts['products'][sku].units_per_case * facts['products'][sku].cases_per_pallet) for sku in skus)
        elif metric == 'days_cover' and on_hand is not None:
            average = _average_demand(facts, day, skus)
            if average and average > 0:
                value = on_hand / average
        elif metric == 'lowest_cover':
            covers = []
            for sku in skus:
                average = _average_demand(facts, day, [sku])
                stock = facts['stock'].get((day, sku))
                if stock is not None and average and average > 0:
                    covers.append(stock / average)
            value = min(covers, default=None)
        point = {'date': day.isoformat(), 'value': value}
        if metric in {'on_hand', 'days_cover', 'pallets'}:
            average = _average_demand(facts, day, skus)
            point['daily_demand'] = average
            point['requested_units'] = demand
            point['days_cover'] = on_hand / average if on_hand is not None and average and average > 0 else None
            safe = []
            for sku in skus:
                daily = _average_demand(facts, day, [sku])
                product = facts['products'][sku]
                safe.append(None if daily is None else daily * facts['suppliers'][product.supplier_id].lead_time_days)
            point['safe_stock_units'] = sum(safe) if all(item is not None for item in safe) else None
        if metric == 'requested_vs_expected':
            run = facts['runs'][day]
            expected = [facts['issued'].get((run.id, day, sku)) for sku in skus] if run else []
            point['expected'] = sum(expected) if expected and all(item is not None for item in expected) else None
            point['expected_run_id'] = run.id if point['expected'] is not None else None
        series.append(point)
        day += timedelta(days=1)
    recent = [{'date': (end - timedelta(days=i)).isoformat(),
               'value': _demand(facts, end - timedelta(days=i), skus)} for i in range(7, 0, -1)]
    latest = series[-1]['value']
    latest_state = 'unknown' if latest is None else 'warning' if threshold and ((latest < threshold['value']) if threshold['operator'] == 'lt' else (latest > threshold['value'])) else 'normal'
    return {'id': widget_id, **spec, 'skus': skus,
            'representative_sku': representative_sku(plan, spec, skus, facts['products']),
            'unit': UNITS[spec['metric']],
            'series': series, 'recent_demand': recent, 'value': latest, 'state': latest_state}


def view(session, plan):
    widgets = ordered(session, plan)
    facts = historical_facts(session, plan, any(w.scope['metric'] == 'requested_vs_expected' for w in widgets))
    return {'widgets': [evaluate(session, plan, w.scope, w.id, facts) for w in widgets],
            'options': options(session, plan), 'facts_through': (plan.week_start - timedelta(days=1)).isoformat(),
            'health': health_snapshot(facts)}
