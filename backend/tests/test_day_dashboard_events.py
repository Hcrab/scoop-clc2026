"""D1 feed contracts: only Scoop events, grouped orders, and clock boundaries."""
from datetime import timedelta

import pandas as pd
import pytest
from sqlalchemy import select, text

from scoop import play
from scoop.config import ORDER_CUTOFF_MINUTE
from test_play import played_week, START
from test_api_state import api


@pytest.fixture(autouse=True)
def isolated_queue_startup(monkeypatch):
    from scoop import simulation_jobs
    # TestClient startup must not initialize the application's persistent queue.
    monkeypatch.setattr(simulation_jobs, 'initialize', lambda: None)


def test_only_scoop_events_without_comparative_receipts(played_week):
    events = played_week['events']
    assert all(event.get('policy', 'scoop') == 'scoop' for event in events)
    assert not any(event['kind'] == 'kept' for event in events)
    assert all('rule' not in event['text'].lower() and 'fewer' not in event['text'].lower()
               and 'more units' not in event['text'].lower() for event in events)
    # The rule retains its distinct physical receipts and full summary for Results.
    assert played_week['runs']['baseline']['per_sku']['arrived'][3][0] == 30
    assert played_week['runs']['scoop']['per_sku']['arrived'][3][0] == 10
    assert set(played_week['summary']) == {'scoop', 'baseline'}


def test_simultaneous_orders_group_without_losing_lines(played_week, monkeypatch):
    original = play.read_sql
    def read(query, **params):
        frame = original(query, **params)
        if 'FROM purchase_suggestions' in query:
            frame['order_date'] = START
        if 'FROM plans' in query:
            frame.at[0, 'summary'] = {'cohort_cards': [{'id': 'fruit', 'skus': ['A', 'B']}]}
        return frame
    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    orders = [event for event in result['events'] if event['kind'] == 'order']
    assert len(orders) == 1
    event = orders[0]
    assert event['text'] == 'Placed 2 orders, 3 cases'
    assert event['minute'] == ORDER_CUTOFF_MINUTE
    assert event['order_count'] == len(event['lines']) == 2
    assert event['cases'] == sum(line['cases'] for line in event['lines']) == 3
    assert [(line['sku'], line['name'], line['cases']) for line in event['lines']] == [('A', 'A', 1), ('B', 'B', 2)]
    assert all(line['expected_arrival'] == (START + timedelta(days=3)).isoformat()
               and line['order_date'] == START.isoformat() and line['card_ids'] == ['fruit']
               for line in event['lines'])


def test_receipts_stockouts_and_heat_keep_separate_clock_boundaries(played_week, monkeypatch):
    original = play.read_sql
    def read(query, **params):
        frame = original(query, **params)
        if 'FROM weather_daily' in query:
            frame['tmax'] = 34.0
        return frame
    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    kinds = {event['kind'] for event in result['events']}
    assert {'order', 'arrival', 'stockout', 'weather'} <= kinds
    assert len({event['id'] for event in result['events']}) == len(result['events'])
    assert result['events'] == sorted(result['events'], key=lambda event: (event['at'], event['id']))
    for event in result['events']:
        # Same predicate used by Play: an event appears only once its instant is reached.
        before = [e for e in result['events'] if e['date'] < event['date'] or
                  (e['date'] == event['date'] and e['minute'] <= event['minute'] - 10)]
        at = [e for e in result['events'] if e['date'] < event['date'] or
              (e['date'] == event['date'] and e['minute'] <= event['minute'])]
        assert event not in before and event in at
        if event['kind'] == 'weather':
            assert event['minute'] == 480
        if event['kind'] == 'arrival':
            i, j = result['dates'].index(event['date']), result['skus'].index(event['sku'])
            assert event['minute'] == result['intraday']['arrival_minutes'][i][j]
            assert event['units'] == result['runs']['scoop']['per_sku']['arrived'][i][j]
        if event['kind'] in {'arrival', 'stockout'} and event['minute'] < ORDER_CUTOFF_MINUTE:
            assert event['date'] not in event['order_dates']
    assert result['runs'] == played_week['runs']  # heat changes presentation only
    assert result['summary'] == played_week['summary']


def test_schema_backed_replay_uses_approved_cases_and_preserves_both_policies(api, monkeypatch):
    from scoop.models import PurchaseSuggestion, WeatherDaily
    client, scope, clock, planning = api
    with scope() as session:
        order = session.scalar(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == 'TESTAPI'))
        order.order_date = START
        order.final_cases = 2
        order.status = 'confirmed'
        session.add(WeatherDaily(date=START, tmax=34., rain_mm=0.))
    def read(query, **params):
        with scope() as session:
            return pd.read_sql(text(query), session.connection(), params=params)
    monkeypatch.setattr(play, 'read_sql', read)
    play._CACHE.clear()
    try:
        result = play.simulate('TESTAPI', START, days=7)
        order = next(event for event in result['events'] if event['kind'] == 'order')
        assert order['cases'] == 2 and order['lines'][0]['sku'] == 'IC001'
        assert result['runs']['scoop']['per_sku']['placed_cases'][0] == [2]
        assert set(result['runs']) == set(result['summary']) == {'scoop', 'baseline'}
        assert all(event.get('policy', 'scoop') == 'scoop' for event in result['events'])
    finally:
        play._CACHE.clear()


def test_approve_watch_play_results_flow_in_disposable_schema(api, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from scoop import db, simulation_jobs
    from scoop.api import service, flow
    from scoop.models import Plan
    client, scope, _, _ = api
    with scope() as session:
        engine = session.bind
        plan = session.get(Plan, 'TESTAPI')
        plan.stage = 'direction'
        plan.summary = {'cohort_model': {'sku_factors': {}, 'cases_overrides': {}}}
    monkeypatch.setattr(db, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
    for module in (service, flow, simulation_jobs):
        monkeypatch.setattr(module, 'session_scope', db.session_scope)
    monkeypatch.setattr(simulation_jobs, '_dispatch', lambda pid, key: simulation_jobs._run(pid, key))
    def read(query, **params):
        with engine.connect() as connection:
            return pd.read_sql(text(query), connection, params=params)
    monkeypatch.setattr(play, 'read_sql', read)
    original = play.simulate
    monkeypatch.setattr(play, 'simulate', lambda pid, week: original(pid, week, days=7))
    play._CACHE.clear()
    try:
        assert client.post('/api/plans/TESTAPI/approve-orders').status_code == 200
        detail = client.get('/api/plans/TESTAPI').json()
        assert detail['flow']['step'] == 'watch'
        simulation = client.get('/api/plans/TESTAPI/simulation').json()
        assert simulation['status'] == 'ready'
        assert simulation_jobs.LOGIC_VERSION == 'same-cold-store-play-v11-demo-carry-cost'
        assert client.put('/api/plans/TESTAPI/flow', json={'step': 'play'}).status_code == 200
        assert client.post('/api/plans/TESTAPI/play', json={}).json() == simulation['result']
        completed = client.post('/api/plans/TESTAPI/play-complete').json()
        assert completed['max_step'] == 'results'
        assert client.put('/api/plans/TESTAPI/flow', json={'step': 'results'}).status_code == 200
    finally:
        play._CACHE.clear()
