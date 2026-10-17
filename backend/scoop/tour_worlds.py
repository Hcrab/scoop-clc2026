"""Coupled illustrative futures, restricted to a private tour recording schema.

Scale the existing seed93 realization, not a new forecast or independent draw.
The planted 1.5 multiplier is independent of the retained weather realization.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re

START = date(2026, 7, 27)
SUMMER_END = date(2026, 8, 10)
GROWTH_END = date(2026, 8, 11)
BRANCHES = ('unchanged', 'summer', 'growing')


def multiplier(branch, day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    if branch not in BRANCHES:
        raise ValueError('Unknown tour future')
    if day < START:
        return Decimal('1.5')
    if branch == 'summer':
        return Decimal('1.5') if day <= SUMMER_END else Decimal(1)
    if branch == 'growing':
        elapsed = min((day - START).days, (GROWTH_END - START).days)
        return Decimal('1.5') + Decimal('0.2') * elapsed / (GROWTH_END - START).days
    return Decimal('1.5')


def units(original, branch, day):
    return int((Decimal(int(original)) * multiplier(branch, day) / Decimal('1.5'))
               .quantize(Decimal(1), rounding=ROUND_HALF_UP))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(',', ':')).encode()).hexdigest()


def private_schema(schema):
    if not re.fullmatch(r'tour_recording_[a-f0-9]{16}', schema):
        raise ValueError('Future replacement requires a private tour recording schema')
    return '"' + schema + '"'


def capture_source(engine, schema):
    """Retained immutable demand input; never selects evaluation ground truth."""
    from sqlalchemy import text
    q = private_schema(schema)
    with engine.begin() as c:
        c.execute(text(f'CREATE TABLE {q}.tour_original_orders AS SELECT * FROM {q}.store_orders'))


def replace_future(engine, schema, branch, skus):
    """Replace demand atomically and remove every persisted replay cache row.

    Call only while the private recorder is idle, after resetting its planning.
    This is intentionally independent of order_hash (which does not hash demand).
    """
    from sqlalchemy import text
    q = private_schema(schema)
    multiplier(branch, START)
    if not skus:
        raise ValueError('Actual matched cohort SKUs are required')
    with engine.begin() as c:
        c.execute(text(f'UPDATE {q}.store_orders t SET ordered_units=o.ordered_units '
                       f'FROM {q}.tour_original_orders o '
                       'WHERE t.date=o.date AND t.store_id=o.store_id AND t.sku=o.sku'))
        # PostgreSQL numeric round is deterministic half-up for nonnegative demand.
        c.execute(text(f'UPDATE {q}.store_orders SET ordered_units=round(ordered_units::numeric * '
                       "CASE WHEN :branch='summer' THEN CASE WHEN date<=:summer_end THEN 1.5 ELSE 1 END "
                       "WHEN :branch='growing' THEN 1.5 + 0.2 * LEAST(date-CAST(:start AS date),15)/15 "
                       'ELSE 1.5 END / 1.5) '
                       'WHERE date>=:start AND sku=ANY(:skus)'),
                  {'branch': branch, 'start': START, 'summer_end': SUMMER_END, 'skus': list(skus)})
        c.execute(text(f'DELETE FROM {q}.simulation_runs'))
        assert c.execute(text(f'SELECT count(*) FROM {q}.simulation_runs')).scalar_one() == 0
    from .demo_worlds import clear_runtime_caches
    clear_runtime_caches()
    from .play import _CACHE
    _CACHE.clear()
    return prove_future(engine, schema, branch, skus)


def prove_future(engine, schema, branch, skus):
    from sqlalchemy import text
    q = private_schema(schema)
    with engine.connect() as c:
        rows = c.execute(text(f'SELECT t.date,t.store_id,t.sku,t.ordered_units,o.ordered_units '
                              f'FROM {q}.store_orders t JOIN {q}.tour_original_orders o '
                              'USING(date,store_id,sku) ORDER BY t.date,t.store_id,t.sku')).all()
        original_count = c.execute(text(f'SELECT count(*) FROM {q}.tour_original_orders')).scalar_one()
        assert c.execute(text(f'SELECT count(*) FROM {q}.store_orders t JOIN '
                              f'{q}.tour_original_orders o USING(date,store_id,sku) '
                              'WHERE t.shipped_units IS DISTINCT FROM o.shipped_units')).scalar_one() == 0
        weather = c.execute(text(f'SELECT date,tmax,rain_mm FROM {q}.weather_daily ORDER BY date')).all()
    assert len(rows) == original_count
    historical, untouched, original, actual = [], [], [], []
    selected = set(skus)
    changed = 0
    for day, store, sku, now, old in rows:
        target = units(old, branch, day) if day >= START and sku in selected else old
        assert now == target, (day, store, sku, now, target)
        original.append([str(day), store, sku, old])
        actual.append([str(day), store, sku, now])
        if day < START:
            assert now == old
            historical.append([str(day), store, sku, now])
        if sku not in selected:
            assert now == old
            untouched.append([str(day), store, sku, now])
        changed += now != old
    return {'branch': branch, 'start': str(START), 'summer_end': str(SUMMER_END),
            'growth_end': str(GROWTH_END), 'matched_skus': sorted(selected),
            'basis': 'same seed93 store-SKU-day realization scaled by planted multiplier / 1.5',
            'rounding': 'nonnegative half-up at store-SKU-day', 'changed_rows': changed,
            'history_hash': digest(historical), 'outside_cohort_hash': digest(untouched),
            'original_demand_hash': digest(original), 'demand_hash': digest(actual),
            'weather_hash': digest([list(row) for row in weather]),
            'multipliers': {day: str(multiplier(branch, day)) for day in
                            ('2026-07-27', '2026-08-10', '2026-08-11')},
            'persisted_replays_cleared': True}


def prove_replay(result):
    """Both policies consume exactly the chosen world's demand matrix."""
    demand = result['demand']
    for policy in ('scoop', 'baseline'):
        assert result['runs'][policy]['per_sku']['demand'] == demand
    return {'policy_demand_equal': True, 'replay_demand_hash': digest(demand),
            'baseline_context_blind': True}


def context_free_control(play, pid, week):
    """Uncached private control: clear both the cache input and live override loader."""
    from . import cohort_context
    saved_read, saved_load = play.read_sql, cohort_context.load_overrides
    def without_context(sql, **params):
        frame = saved_read(sql, **params)
        return frame.iloc[:0] if sql == "SELECT value FROM settings WHERE key = 'cohort_overrides'" else frame
    play.read_sql = without_context
    cohort_context.load_overrides = lambda *args, **kwargs: []
    play._CACHE.clear()
    try:
        return play.simulate(pid, week)
    finally:
        play.read_sql, cohort_context.load_overrides = saved_read, saved_load


def historical_evidence(snapshot):
    """Only pre-branch observations/report, never order-ledger presentation."""
    detail = snapshot['detail']
    summary = detail['plan']['summary']
    return {key: detail.get(key) for key in ('raw_trends', 'findings')} | {
        'cards': sorted(({key: card.get(key) for key in
                          ('id','name','skus','districts','tag_path','daily','drilldown')}
                         for card in detail.get('cohort_cards', [])), key=lambda c:c['id']),
        'report': {key: summary.get(key) for key in
                   ('findings','weekly_review','weak_reviews','discussion','model_run')}}


def preserve_questions(bundle, previous):
    """Keep genuine recordings with their original, hashable evidence snapshot."""
    evidence = previous.get('question_evidence', previous['base'])
    if historical_evidence(evidence) != historical_evidence(bundle['base']):
        raise ValueError('Recorded question history/report changed; cannot reuse recordings')
    for answer in previous['questions'].values():
        if answer is not None:
            assert answer['snapshot_hash'] == digest(evidence)
            assert answer['source_order_hash'] == evidence['simulation']['order_hash']
    bundle['questions'] = previous['questions']
    bundle['question_evidence'] = evidence
