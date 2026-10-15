"""One local, persisted simulation queue. Reads never start work."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from .db import engine, session_scope
from .models import Plan, PurchaseSuggestion, Setting, SimulationRun

LOGIC_VERSION = 'matched-space-play-v4'
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='scoop-simulation')
_dispatch_lock = Lock()
_dispatched: set[tuple[str, str]] = set()


def order_hash(session, plan: Plan) -> str:
    """Fingerprint only inputs that can change the physical replay."""
    session.flush()
    orders = session.scalars(select(PurchaseSuggestion).where(
        PurchaseSuggestion.plan_id == plan.id).order_by(PurchaseSuggestion.sku)).all()
    lines = [(o.sku, o.order_date.isoformat(), int(o.final_cases if o.final_cases is not None
              else max(0, o.suggested_cases-o.capacity_cut_cases))) for o in orders]
    setting = session.get(Setting, 'cohort_overrides')
    overrides = json.loads(setting.value) if setting else []
    overrides = [{k: x.get(k) for k in ('tag_path', 'districts', 'type', 'value', 'expires_on')}
                 for x in overrides if not x.get('expires_on') or x['expires_on'] >= plan.week_start.isoformat()]
    # Physical inputs and model identity matter; dashboard, report and discussion do not.
    queries = [
        "SELECT sku, units_per_case, cases_per_pallet, price_hkd, cost_hkd, moq_cases, supplier_id FROM products ORDER BY sku",
        "SELECT id, lead_time_days, order_weekday, review_days FROM suppliers ORDER BY id",
        "SELECT id, capacity_pallets FROM nodes ORDER BY id",
        "SELECT sku, on_hand_units FROM node_inventory WHERE date=:day ORDER BY sku",
        "SELECT id, sku, cases, order_date, expected_date, received_date FROM purchase_orders WHERE source='history' AND order_date<:start AND (received_date IS NULL OR received_date>=:start) ORDER BY id",
        "SELECT id, trained_through FROM model_runs WHERE trained_through<:start ORDER BY trained_through DESC, created_at DESC LIMIT 1",
    ]
    physical = [[list(row) for row in session.execute(text(sql), {'day': plan.week_start-timedelta(days=1), 'start': plan.week_start})]
                for sql in queries]
    seed = session.get(Setting, 'seed')
    payload = [LOGIC_VERSION, plan.id, plan.week_start, lines, plan.goal, plan.service_level,
               (plan.summary or {}).get('cohort_model'),
               overrides, seed.value if seed else None, physical]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def initialize() -> None:
    SimulationRun.__table__.create(engine, checkfirst=True)
    # Work interrupted by a process restart can be resumed safely.
    with session_scope() as session:
        runs = session.scalars(select(SimulationRun).where(SimulationRun.status.in_(['queued', 'running']))).all()
        keys = [(r.plan_id, r.order_hash) for r in runs]
        for run in runs:
            if run.status == 'running':
                run.status = 'queued'
                run.started_at = None
    for key in keys:
        _dispatch(*key)


def _dispatch(plan_id: str, key: str) -> None:
    pair = (plan_id, key)
    with _dispatch_lock:
        if pair in _dispatched:
            return
        _dispatched.add(pair)
    _executor.submit(_run, plan_id, key)


def enqueue(plan_id: str, retry: bool = False) -> dict:
    with session_scope() as session:
        plan = session.get(Plan, plan_id)
        if plan is None:
            return {'status': 'not_started', 'order_hash': None}
        key = order_hash(session, plan)
        statement = insert(SimulationRun).values(plan_id=plan_id, order_hash=key,
                     status='queued', queued_at=datetime.now()).on_conflict_do_nothing()
        session.execute(statement)
        run = session.get(SimulationRun, (plan_id, key))
        if retry and run.status == 'failed':
            run.status = 'queued'
            run.queued_at = datetime.now()
            run.started_at = run.completed_at = None
            run.elapsed_seconds = None
            run.error = None
            run.result = None
        queued = run.status == 'queued'
        response = view(run)
    if queued:
        _dispatch(plan_id, key)
    return response


def view(run: SimulationRun | None, key: str | None = None) -> dict:
    if run is None:
        return {'status': 'not_started', 'order_hash': key, 'queued_at': None,
                'started_at': None, 'completed_at': None, 'elapsed_seconds': None}
    result = {'status': run.status, 'order_hash': run.order_hash,
              'queued_at': run.queued_at.isoformat() if run.queued_at else None,
              'started_at': run.started_at.isoformat() if run.started_at else None,
              'completed_at': run.completed_at.isoformat() if run.completed_at else None,
              'elapsed_seconds': run.elapsed_seconds}
    if run.status == 'ready':
        result['result'] = run.result
    if run.status == 'failed':
        result['error'] = run.error
    return result


def status(session, plan: Plan) -> dict:
    key = order_hash(session, plan)
    return view(session.get(SimulationRun, (plan.id, key)), key)


def _run(plan_id: str, key: str) -> None:
    from .demo_gate import gate
    with gate.activity():
        _run_active(plan_id, key)


def _run_active(plan_id: str, key: str) -> None:
    try:
        with session_scope() as session:
            run = session.get(SimulationRun, (plan_id, key))
            if run is None or run.status != 'queued':
                return
            plan = session.get(Plan, plan_id)
            if plan is None or order_hash(session, plan) != key:
                run.status = 'failed'
                run.error = 'Orders changed before this run started.'
                run.completed_at = datetime.now()
                return
            run.status = 'running'
            run.started_at = datetime.now()
            week = plan.week_start
        started = monotonic()
        from .play_comparison import prepare
        from .api.service import clean
        result = clean(prepare(plan_id, week))
        elapsed = monotonic() - started
        with session_scope() as session:
            run = session.get(SimulationRun, (plan_id, key))
            plan = session.get(Plan, plan_id)
            if run is None:
                return
            if plan is None or order_hash(session, plan) != key:
                run.status = 'failed'
                run.error = 'Orders changed during this run.'
            else:
                run.status = 'ready'
                run.result = result
            run.completed_at = datetime.now()
            run.elapsed_seconds = elapsed
    except Exception as exc:
        try:
            with session_scope() as session:
                run = session.get(SimulationRun, (plan_id, key))
                if run is not None:
                    run.status = 'failed'
                    run.error = f'{type(exc).__name__}: {exc}'[:500]
                    run.completed_at = datetime.now()
        except Exception:
            pass
    finally:
        with _dispatch_lock:
            _dispatched.discard((plan_id, key))
