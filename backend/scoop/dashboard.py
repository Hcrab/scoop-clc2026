"""Plan-owned dashboard widgets backed by observed history."""
from collections import defaultdict
from datetime import timedelta
from math import isfinite
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from .models import Product, Store, StoreOrder, NodeInventory, WatchItem, DailyExpectation, ModelRun
from .ai.exploration_tools import _groups

METRICS = {'on_hand', 'lost_units', 'demand', 'fill_rate', 'days_cover',
           'pallets', 'requested_vs_expected'}
UNITS = {'on_hand': 'units', 'lost_units': 'units', 'demand': 'units',
         'fill_rate': 'ratio', 'days_cover': 'days', 'pallets': 'pallets',
         'requested_vs_expected': 'units'}


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
        return sorted(set(group.skus) & set(products))
    card = next((c for c in (plan.summary or {}).get('cohort_cards', []) if c['id'] == key), None)
    if card is None: raise HTTPException(422, 'Unknown plan cohort')
    return sorted(set(card.get('skus', [])) & set(products))


def active(session, plan):
    return [w for w in session.scalars(select(WatchItem).where(WatchItem.plan_id == plan.id, WatchItem.status == 'active')) if isinstance(w.scope, dict) and 'metric' in w.scope]


def ordered(session, plan):
    items = active(session, plan)
    positions = {wid: i for i, wid in enumerate((plan.summary or {}).get('dashboard_order', []))}
    return sorted(items, key=lambda w: (positions.get(w.id, len(positions)), w.id))


def initialize(session, plan):
    if 'dashboard_order' in (plan.summary or {}): return
    # Old watches have a different scope shape and cannot be interpreted as widgets.
    for watch in session.scalars(select(WatchItem).where(WatchItem.plan_id == plan.id, WatchItem.status == 'active')):
        watch.status = 'archived'
        watch.title = ('~' + watch.id + ' ' + watch.title)[:160]
    specs = []
    for card in (plan.summary or {}).get('cohort_cards', [])[:2]:
        specs.append({'title': f"{card.get('name') or card['id']} demand vs expected", 'scope': {'kind': 'cohort', 'key': card['id']}, 'metric': 'requested_vs_expected', 'threshold': None})
    specs += [{'title': 'Warehouse units on hand', 'scope': {'kind': 'warehouse', 'key': ''}, 'metric': 'on_hand', 'threshold': None},
              {'title': 'Warehouse pallets', 'scope': {'kind': 'warehouse', 'key': ''}, 'metric': 'pallets', 'threshold': None},
              {'title': 'Store fill rate', 'scope': {'kind': 'warehouse', 'key': ''}, 'metric': 'fill_rate', 'threshold': None}]
    ids = []
    for spec in specs:
        widget = save(session, plan, spec, origin='baseline')
        ids.append(widget.id)
    plan.summary = {**(plan.summary or {}), 'dashboard_order': ids}
    session.flush()


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


def evaluate(session, plan, spec, widget_id='preview'):
    spec = canonical(spec)
    skus = resolve(session, plan, spec)
    selected = set(skus)
    card = next((c for c in (plan.summary or {}).get('cohort_cards', []) if c['id'] == spec['scope']['key']), None) if spec['scope']['kind'] == 'cohort' else None
    districts = set(card.get('districts', [])) if card else set()
    stores = {store.id: store.district for store in session.scalars(select(Store))}
    scoped_stores = {sid for sid, district in stores.items() if district in districts} if districts else set(stores)
    end = plan.week_start
    start = end - timedelta(days=28)
    warmup = start - timedelta(days=7)
    orders = list(session.scalars(select(StoreOrder).where(StoreOrder.date >= warmup, StoreOrder.date < end)))
    inventory = list(session.scalars(select(NodeInventory).where(NodeInventory.date >= start, NodeInventory.date < end)))
    products = {p.sku: p for p in session.scalars(select(Product))}
    requested = defaultdict(float); shipped = defaultdict(float); per_sku = defaultdict(float)
    order_dates = set()
    for order in orders:
        if order.store_id not in scoped_stores: continue
        order_dates.add(order.date)
        if order.sku in selected:
            requested[order.date] += order.ordered_units
            shipped[order.date] += order.shipped_units
            per_sku[(order.date, order.sku)] += order.ordered_units
    stock = defaultdict(dict)
    for row in inventory:
        if row.sku in selected: stock[row.date][row.sku] = row.on_hand_units
    expected = defaultdict(float); expected_dates = set()
    if spec['metric'] == 'requested_vs_expected':
        # Existing issued forecasts only; never run or train a model for a widget.
        run = session.scalar(select(ModelRun).where(ModelRun.trained_through < end).order_by(ModelRun.trained_through.desc(), ModelRun.created_at.desc()).limit(1))
        if run:
            forecasts = session.scalars(select(DailyExpectation).where(DailyExpectation.run_id == run.id, DailyExpectation.date >= start, DailyExpectation.date < end, DailyExpectation.sku.in_(skus), DailyExpectation.store_id.in_(scoped_stores)))
            for row in forecasts:
                expected[row.date] += row.p50
                expected_dates.add(row.date)
    series = []
    threshold = spec['threshold']
    latest_state = 'unknown'
    day = start
    while day < end:
        value = None
        metric = spec['metric']
        if metric in {'demand', 'lost_units', 'fill_rate', 'requested_vs_expected'} and day in order_dates:
            demand = requested[day]
            if metric in {'demand', 'requested_vs_expected'}: value = demand
            elif metric == 'lost_units': value = demand - shipped[day]
            elif demand > 0: value = shipped[day] / demand
        elif metric in {'on_hand', 'pallets', 'days_cover'} and day in stock and set(stock[day]) == selected:
            if metric == 'on_hand': value = sum(stock[day].values())
            elif metric == 'pallets':
                value = sum(units / (products[sku].units_per_case * products[sku].cases_per_pallet)
                            for sku, units in stock[day].items())
            elif all(day - timedelta(days=i) in order_dates for i in range(1, 8)):
                demand = sum(per_sku[(day - timedelta(days=i), sku)] for i in range(1, 8) for sku in skus)
                if demand > 0: value = sum(stock[day].values()) / (demand / 7)
        state = 'unknown' if value is None else 'warning' if threshold and ((value < threshold['value']) if threshold['operator'] == 'lt' else (value > threshold['value'])) else 'normal'
        point = {'date': day.isoformat(), 'value': value}
        if metric == 'requested_vs_expected': point['expected'] = expected[day] if day in expected_dates else None
        series.append(point)
        latest_state = state
        day += timedelta(days=1)
    return {'id': widget_id, **spec, 'skus': skus, 'unit': UNITS[spec['metric']],
            'series': series, 'value': series[-1]['value'], 'state': latest_state}


def view(session, plan):
    initialize(session, plan)
    return {'widgets': [evaluate(session, plan, w.scope, w.id) for w in ordered(session, plan)],
            'options': options(session, plan), 'facts_through': (plan.week_start - timedelta(days=1)).isoformat()}
