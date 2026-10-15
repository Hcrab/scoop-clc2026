"""Persisted replay jobs through real approval/edit endpoints in a disposable world."""
from datetime import datetime

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from test_api_state import api
from scoop import db, play, simulation_jobs
from scoop.api import service, flow
from scoop.models import Plan, PurchaseSuggestion, SimulationRun


def test_approval_edit_and_widget_flow_use_committed_quantities(api, monkeypatch):
    client, fixture_scope, _, _ = api
    with fixture_scope() as session:
        disposable_engine = session.bind
        plan = session.get(Plan, 'TESTAPI')
        plan.stage = 'direction'
        plan.summary = {'cohort_model': {'sku_factors': {}, 'cases_overrides': {}}}

    # Route production sessions and the worker to the fixture schema. This exercises
    # db.py's after-commit queue, not an in-memory copy of the business logic.
    monkeypatch.setattr(db, 'SessionLocal', sessionmaker(bind=disposable_engine, expire_on_commit=False))
    monkeypatch.setattr(service, 'session_scope', db.session_scope)
    monkeypatch.setattr(flow, 'session_scope', db.session_scope)
    monkeypatch.setattr(simulation_jobs, 'session_scope', db.session_scope)
    monkeypatch.setattr(simulation_jobs, '_dispatch', lambda pid, key: simulation_jobs._run(pid, key))
    def read_sql(sql, **params):
        with disposable_engine.connect() as connection:
            return pd.read_sql(text(sql), connection, params=params)

    monkeypatch.setattr(play, 'read_sql', read_sql)
    original_simulate = play.simulate
    calls = []

    def simulate(pid, week, **kwargs):
        assert kwargs == {}
        with db.session_scope() as session:
            order = session.get(PurchaseSuggestion, (pid, 'IC001'))
            calls.append(order.final_cases if order.final_cases is not None else order.suggested_cases)
        return original_simulate(pid, week, days=7, **kwargs)

    monkeypatch.setattr(play, 'simulate', simulate)
    play._CACHE.clear()
    try:
        initial = client.get('/api/plans/TESTAPI/simulation').json()
        assert initial['status'] == 'not_started'
        assert client.get('/api/plans/TESTAPI/simulation').json() == initial
        assert client.post('/api/plans/TESTAPI/play', json={}).status_code == 409
        assert calls == []

        approved = client.post('/api/plans/TESTAPI/approve-orders')
        assert approved.status_code == 200, approved.text
        first = client.get('/api/plans/TESTAPI/simulation').json()
        assert first['status'] == 'ready' and first['result']['runs']['scoop']['per_sku']['demand']
        assert 'matched' not in first['result']
        assert simulation_jobs.LOGIC_VERSION == 'same-cold-store-play-v5'
        assert client.post('/api/plans/TESTAPI/play', json={}).json() == first['result']
        assert calls == [3]
        assert client.post('/api/plans/TESTAPI/approve-orders').status_code == 200
        assert calls == [3]

        added = client.post('/api/plans/TESTAPI/dashboard', json={
            'title': 'Stock', 'scope': {'kind': 'sku', 'key': 'IC001'}, 'metric': 'on_hand'})
        assert added.status_code == 200, added.text
        assert client.put('/api/plans/TESTAPI/flow', json={'step': 'play'}).status_code == 200
        assert client.get('/api/plans/TESTAPI').json()['flow']['step'] == 'play'
        assert client.get('/api/plans/TESTAPI/simulation').json()['order_hash'] == first['order_hash']
        assert calls == [3]
        completed = client.post('/api/plans/TESTAPI/play-complete')
        assert completed.json()['step'] == 'play'
        assert completed.json()['max_step'] == 'results'

        edited = client.post('/api/plans/TESTAPI/orders/bulk', json={
            'filter': {'skus': ['IC001']}, 'change': {'type': 'set_cases', 'value': 4}})
        assert edited.status_code == 200, edited.text
        second = client.get('/api/plans/TESTAPI/simulation').json()
        assert second['status'] == 'ready'
        assert second['order_hash'] != first['order_hash']
        assert calls == [3, 4]
        detail = client.get('/api/plans/TESTAPI').json()
        assert detail['flow']['step'] == detail['flow']['max_step'] == 'orders'
        assert detail['flow']['notice']
        assert detail['orders'][0]['effective_cases'] == 4
        assert second['result']['runs']['scoop']['per_sku']['placed_cases'][0][0] == 4
        assert any(widget['title'] == 'Stock' for widget in detail['dashboard']['widgets'])

        with db.session_scope() as session:
            assert session.get(SimulationRun, ('TESTAPI', first['order_hash'])).status == 'ready'
            assert session.get(SimulationRun, ('TESTAPI', second['order_hash'])).status == 'ready'
        assert client.post('/api/plans/TESTAPI/approve-orders').status_code == 200
        assert calls == [3, 4]

        # Returning to a quantity whose earlier run was discarded must schedule it
        # again, rather than leaving that valid order stuck in a failed cache entry.
        with db.session_scope() as session:
            previous = session.get(SimulationRun, ('TESTAPI', second['order_hash']))
            previous.status = 'failed'
            previous.result = None
            previous.error = 'Orders changed during this run.'
        for amount in (3, 4):
            changed = client.post('/api/plans/TESTAPI/orders/bulk', json={
                'filter': {'skus': ['IC001']}, 'change': {'type': 'set_cases', 'value': amount}})
            assert changed.status_code == 200, changed.text
        retried = client.get('/api/plans/TESTAPI/simulation').json()
        assert retried['status'] == 'ready'
        assert retried['order_hash'] == second['order_hash']
        assert calls == [3, 4, 3, 4]
    finally:
        play._CACHE.clear()


def test_current_hash_never_serves_old_ready_result(api, monkeypatch):
    client, scope, _, _ = api
    monkeypatch.setattr(flow, 'session_scope', scope)
    with scope() as session:
        session.get(Plan, 'TESTAPI').stage = 'execute'
        session.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).final_cases = 3
        session.add(SimulationRun(plan_id='TESTAPI', order_hash='old-key', status='ready',
                                  queued_at=datetime(2026, 7, 6), result={'stale': True}))
    current = client.get('/api/plans/TESTAPI/simulation')
    assert current.status_code == 200
    assert current.json()['status'] == 'not_started'
    assert 'result' not in current.json()


def test_queued_key_coalesces_and_stale_worker_is_discarded(api, monkeypatch):
    _, scope, _, _ = api
    with scope() as session:
        disposable_engine = session.bind
    monkeypatch.setattr(db, 'SessionLocal', sessionmaker(bind=disposable_engine, expire_on_commit=False))
    monkeypatch.setattr(simulation_jobs, 'session_scope', db.session_scope)
    monkeypatch.setattr(simulation_jobs, '_dispatch', lambda *_: None)
    first = simulation_jobs.enqueue('TESTAPI')
    second = simulation_jobs.enqueue('TESTAPI')
    assert first['order_hash'] == second['order_hash']
    with scope() as session:
        assert session.scalar(select(func.count()).select_from(SimulationRun)) == 1

    def edit_during_run(pid, week):
        with db.session_scope() as session:
            session.get(PurchaseSuggestion, (pid, 'IC001')).final_cases = 4
        return {'stale': True}

    monkeypatch.setattr(play, 'simulate', edit_during_run)
    simulation_jobs._run('TESTAPI', first['order_hash'])
    with scope() as session:
        old = session.get(SimulationRun, ('TESTAPI', first['order_hash']))
        assert old.status == 'failed' and old.result is None
        current = simulation_jobs.status(session, session.get(Plan, 'TESTAPI'))
        assert current['status'] == 'not_started'
        assert current['order_hash'] != first['order_hash']
