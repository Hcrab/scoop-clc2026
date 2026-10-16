"""Small, deterministic stock-flow checks for the two Play policies."""

from datetime import date, timedelta

import pandas as pd
import pytest

from scoop import play


START = date(2026, 7, 13)
SKUS = ("A", "B")
OPENING = {"A": 5.0, "B": 2.0}


@pytest.fixture
def played_week(monkeypatch):
    play._CACHE.clear()
    products = pd.DataFrame(
        [
            {"sku": "A", "name": "A", "brand": "Test", "supplier_id": "SUP01", "price_hkd": 4.0,
             "cost_hkd": 2.0, "units_per_case": 10, "cases_per_pallet": 10,
             "moq_cases": 1, "lead_time_days": 3, "order_weekday": 0, "review_days": 7},
            {"sku": "B", "name": "B", "brand": "Test", "supplier_id": "SUP02", "price_hkd": 3.0,
             "cost_hkd": 1.0, "units_per_case": 5, "cases_per_pallet": 10,
             "moq_cases": 1, "lead_time_days": 3, "order_weekday": 1, "review_days": 7},
        ]
    )
    suggestions = pd.DataFrame(
        [
            {"sku": "A", "order_date": START, "suggested_cases": 1,
             "capacity_cut_cases": 0, "final_cases": 1, "status": "confirmed"},
            {"sku": "B", "order_date": START + timedelta(days=1),
             "suggested_cases": 2, "capacity_cut_cases": 0,
             "final_cases": 2, "status": "confirmed"},
        ]
    )
    # The 28 historical days also give the mechanical rule a fixed demand rate.
    store_orders = pd.DataFrame(
        {"date": [day for day in (START + timedelta(days=i) for i in range(-28, 7)) for _ in SKUS],
         "sku": list(SKUS) * 35,
         "u": [units for _ in range(35) for units in (3.0, 2.0)]}
    )
    transit = pd.DataFrame(
        [
            {"sku": "A", "units": 4.0, "received_date": None,
             "expected_date": START + timedelta(days=2)},
            {"sku": "B", "units": 6.0, "received_date": START,
             "expected_date": START + timedelta(days=1)},
        ]
    )

    def read_sql(query, **params):
        if "FROM purchase_suggestions" in query:
            assert params == {"p": "test-plan"}
            return suggestions.copy()
        if "FROM plans" in query:
            return pd.DataFrame({"summary": [{}], "goal": ["margin"], "service_level": [None]})
        if "FROM settings" in query:
            return pd.DataFrame({"value": ["[]"]})
        if "FROM products p JOIN suppliers" in query:
            return products.copy()
        if "FROM store_orders" in query:
            return store_orders.copy()
        if "FROM node_inventory" in query:
            assert params == {"d": START - timedelta(days=1)}
            return pd.DataFrame({"sku": SKUS, "on_hand_units": list(OPENING.values())})
        if "FROM purchase_orders" in query:
            assert params == {"d": START}
            return transit.copy()
        if "FROM weather_daily" in query:
            return pd.DataFrame({"date": [START + timedelta(days=i) for i in range(7)],
                                 "tmax": [25.0] * 7})
        if "FROM nodes" in query:
            return pd.DataFrame({"capacity_pallets": [100.0]})
        if "FROM model_runs" in query:
            return pd.DataFrame(columns=["id", "trained_through"])
        raise AssertionError(f"Unexpected database read: {query}")

    monkeypatch.setattr(play, "read_sql", read_sql)
    try:
        yield play.simulate("test-plan", START, days=7)
    finally:
        play._CACHE.clear()


def test_policies_share_opening_transit_and_daily_demand(played_week):
    result = played_week
    scoop = result["runs"]["scoop"]["per_sku"]
    baseline = result["runs"]["baseline"]["per_sku"]
    assert result["skus"] == list(SKUS)

    # Recover opening stock from the first day's stock-flow equation.
    for run in (scoop, baseline):
        for i, sku in enumerate(SKUS):
            assert run["on_hand"][0][i] + run["shipped"][0][i] - run["arrived"][0][i] == pytest.approx(OPENING[sku])
        for day, demand in enumerate(result["demand"]):
            for i in range(len(SKUS)):
                assert run["demand"][day][i] == pytest.approx(demand[i])
                assert run["shipped"][day][i] + run["lost"][day][i] == pytest.approx(demand[i])

    # Historical POs have both a recorded receipt and a pending expected date.
    assert scoop["arrived"][0] == baseline["arrived"][0] == [0.0, 6.0]
    assert scoop["arrived"][2] == baseline["arrived"][2] == [4.0, 0.0]
    assert scoop["arrived"][3][0] == 10.0
    assert baseline["arrived"][3][0] == 30.0
    assert scoop["arrived"][4][1] == 10.0
    assert baseline["arrived"][4][1] == 20.0
    assert any(sum(day) > 0 for day in scoop["lost"])


def test_each_policy_conserves_stock_per_sku_each_day(played_week):
    for policy in ("scoop", "baseline"):
        run = played_week["runs"][policy]["per_sku"]
        for i, sku in enumerate(SKUS):
            opening = OPENING[sku]
            for day in range(played_week["days"]):
                ending = run["on_hand"][day][i]
                assert opening + run["arrived"][day][i] == pytest.approx(
                    run["shipped"][day][i] + ending
                ), f"{policy} {sku} day {day}"
                opening = ending
            assert OPENING[sku] + sum(row[i] for row in run["arrived"]) == pytest.approx(
                sum(row[i] for row in run["shipped"]) + opening
            ), f"{policy} {sku} full period"


def test_autopilot_refits_each_week_even_without_monday_orders(played_week, monkeypatch):
    from scoop import planning
    from scoop.algorithms import cohort_model
    original_read = play.read_sql

    def read(query, **params):
        if 'FROM store_orders' in query:
            return pd.DataFrame({'date': [START+timedelta(days=i) for i in range(-28, 21) for _ in SKUS],
                                 'sku': list(SKUS)*49, 'u': [v for _ in range(49) for v in (3., 2.)]})
        frame = original_read(query, **params)
        if 'FROM products p JOIN suppliers' in query:
            frame['order_weekday'] = 1
        return frame

    fitted = []
    monkeypatch.setattr(play, 'read_sql', read)
    monkeypatch.setattr(cohort_model, 'fit', lambda plan: fitted.append(plan.week_start) or {'sku_factors': {}})
    monkeypatch.setattr(planning, 'detect', lambda day: [])
    calls = []

    def suggest(*args, **kwargs):
        calls.append((args, kwargs))
        return pd.DataFrame({'sku': list(SKUS), 'final_cases': [1, 1]})

    monkeypatch.setattr(planning, 'suggest_orders', suggest)
    result = play.simulate('test-plan', START, days=21)
    assert fitted == [START+timedelta(days=7), START+timedelta(days=14)]
    assert result['days'] == 21
    for policy in ('scoop', 'baseline'):
        placed = result['runs'][policy]['per_sku']['placed_cases']
        assert sum(placed[8]) > 0
    assert all(kwargs['goal'] == 'margin' and kwargs['service_level'] is None for _, kwargs in calls)
    assert any(event['date'] == (START + timedelta(days=8)).isoformat() and
               event['kind'] == 'order' and event['automatic'] for event in result['events'])


def test_default_window_covers_arrival_and_caps_at_calendar(played_week, monkeypatch):
    from scoop import planning
    from scoop.algorithms import cohort_model
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM products p JOIN suppliers' in query:
            frame['lead_time_days'] = 18
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    monkeypatch.setattr(cohort_model, 'fit', lambda plan: {})
    monkeypatch.setattr(planning, 'detect', lambda day: [])
    monkeypatch.setattr(planning, 'suggest_orders', lambda *args, **kwargs:
                        pd.DataFrame({'sku': list(SKUS), 'final_cases': [0, 0]}))
    assert play.simulate('test-plan', START)['days'] == 21
    monkeypatch.setattr(play, 'MAX_DAY', START + timedelta(days=9))
    clipped = play.simulate('test-plan', START)
    assert clipped['days'] == 10
    assert clipped['end'] == (START + timedelta(days=9)).isoformat()
    assert len(clipped['demand']) == len(clipped['dates']) == 10


def test_default_window_uses_only_positive_orders(played_week, monkeypatch):
    from scoop import planning
    from scoop.algorithms import cohort_model
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM products p JOIN suppliers' in query:
            frame.loc[frame.sku == 'B', 'lead_time_days'] = 18
        if 'FROM purchase_suggestions' in query:
            frame.loc[frame.sku == 'B', 'final_cases'] = 0
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    monkeypatch.setattr(cohort_model, 'fit', lambda plan: {})
    monkeypatch.setattr(planning, 'detect', lambda day: [])
    monkeypatch.setattr(planning, 'suggest_orders', lambda *args, **kwargs:
                        pd.DataFrame({'sku': list(SKUS), 'final_cases': [0, 0]}))
    assert play.simulate('test-plan', START)['days'] == 10


def test_affected_summary_excludes_unchanged_sku_and_includes_cards(played_week, monkeypatch):
    original_read = play.read_sql
    card = {'skus': ['C']}

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM products p JOIN suppliers' in query:
            return pd.concat([frame, pd.DataFrame([{'sku': 'C', 'name': 'C', 'brand': 'Test',
                'price_hkd': 2., 'cost_hkd': 1., 'units_per_case': 10, 'cases_per_pallet': 10,
                'moq_cases': 1, 'lead_time_days': 3, 'order_weekday': 0, 'review_days': 7}])], ignore_index=True)
        if 'FROM node_inventory' in query:
            return pd.concat([frame, pd.DataFrame([{'sku': 'C', 'on_hand_units': 100.}])], ignore_index=True)
        if 'FROM plans' in query:
            frame.at[0, 'summary'] = {'cohort_cards': []}
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    assert result['affected_skus'] == ['A', 'B']
    assert result['summary']['scoop']['ending_on_hand'] - result['affected_summary']['scoop']['ending_on_hand'] == 100
    assert result['affected_summary']['scoop']['lost_units'] == result['summary']['scoop']['lost_units']
    assert result['affected_comparison']['units_saved'] == result['summary']['baseline']['lost_units'] - result['summary']['scoop']['lost_units']

    def with_card(query, **params):
        frame = read(query, **params)
        if 'FROM plans' in query:
            frame.at[0, 'summary'] = {'cohort_cards': [card]}
        return frame

    monkeypatch.setattr(play, 'read_sql', with_card)
    assert play.simulate('test-plan', START, days=7)['affected_skus'] == ['A', 'B', 'C']


def test_cache_invalidates_order_date_and_context(played_week, monkeypatch):
    original_read = play.read_sql
    state = {'day': START, 'context': '[]', 'capacity': 100.}

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM purchase_suggestions' in query:
            frame.loc[frame.sku == 'A', 'order_date'] = state['day']
        if 'FROM settings' in query:
            frame.at[0, 'value'] = state['context']
        if 'FROM nodes' in query:
            frame.at[0, 'capacity_pallets'] = state['capacity']
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    first = play.simulate('test-plan', START, days=7)
    assert play.simulate('test-plan', START, days=7) is first
    state['day'] = START + timedelta(days=1)
    moved = play.simulate('test-plan', START, days=7)
    assert moved is not first
    assert moved['runs']['scoop']['per_sku']['arrived'][3][0] != first['runs']['scoop']['per_sku']['arrived'][3][0]
    state['context'] = '[{"id":"updated"}]'
    changed = play.simulate('test-plan', START, days=7)
    assert changed is not moved
    state['capacity'] = 90.
    resized = play.simulate('test-plan', START, days=7)
    assert resized is not changed
    assert resized['capacity_pallets'] == 90.


def test_proportional_receiving_uses_whole_units_and_stable_remainders():
    stock = pd.Series({'A': 4., 'B': 0.})
    due = pd.Series({'A': 6., 'B': 4.})
    upp = pd.Series({'A': 100., 'B': 50.})
    assert play._admit_receipts(stock, due, upp, .10).to_dict() == {'A': 2., 'B': 2.}
    assert play._admit_receipts(stock, due, upp, .20).to_dict() == due.to_dict()


def test_saturated_receipts_defer_without_losing_pipeline(played_week, monkeypatch):
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM nodes' in query:
            frame.at[0, 'capacity_pallets'] = .12
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    assert 'matched' not in result
    for policy in ('scoop', 'baseline'):
        run = result['runs'][policy]
        rows = run['per_sku']
        assert any(sum(day) > 0 for day in rows['deferred'])
        assert rows['deferred'][0][1] > 0
        assert rows['arrived'][1][1] > 0
        assert result['summary'][policy]['days_over_capacity'] == 0
        assert result['summary'][policy]['peak_pallets'] == pytest.approx(
            max(day['pallets_pre_ship'] for day in run['daily']))
        for day in run['daily']:
            assert day['pallets_pre_ship'] <= .12 + 1e-9
        for hour in run['hourly']['on_hand']:
            assert hour[0] / 100 + hour[1] / 50 <= .12 + 1e-9
        for day, arrivals in enumerate(rows['arrived']):
            opening = [OPENING[s] for s in SKUS] if day == 0 else rows['on_hand'][day - 1]
            for step, minute in enumerate(result['intraday']['minutes']):
                level = [opening[j] + (arrivals[j] if minute >= result['intraday']['arrival_minutes'][day][j] else 0)
                         - rows['shipped'][day][j] * result['intraday']['dispatch_cdf'][step]
                         for j in range(len(SKUS))]
                assert level[0] / 100 + level[1] / 50 <= .12 + 1e-9
        initial_pipeline = 10.
        ordered_units = sum(day[0] * 10 + day[1] * 5 for day in rows['placed_cases'])
        received = sum(map(sum, rows['arrived']))
        pending = sum(run['pipeline_units_after'].values())
        assert initial_pipeline + ordered_units == pytest.approx(received + pending)
        assert pending == pytest.approx(sum(sum(values.values()) for values in run['pending_after'].values()))
        if policy == 'scoop':
            assert rows['placed_cases'][0][0] == 1
            assert rows['placed_cases'][1][1] == 2
    for event in result['events']:
        if event['kind'] == 'arrival':
            i = result['dates'].index(event['date'])
            j = result['skus'].index(event['sku'])
            assert event['units'] == result['runs'][event['policy']]['per_sku']['arrived'][i][j]


def test_overfull_opening_stock_fails_explicitly(played_week, monkeypatch):
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM nodes' in query:
            frame.at[0, 'capacity_pallets'] = .08
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    with pytest.raises(ValueError, match='Opening cold-store inventory'):
        play.simulate('test-plan', START, days=7)


def test_empty_affected_set_has_zero_quantities(played_week, monkeypatch):
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM purchase_suggestions' in query:
            return frame.iloc[0:0].copy()
        if 'FROM node_inventory' in query:
            frame['on_hand_units'] = 1000.
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START)
    assert result['days'] == 7
    assert result['affected_skus'] == []
    for policy in ('scoop', 'baseline'):
        values = result['affected_summary'][policy]
        assert values['fill_rate'] == 1
        assert all(values[key] == 0 for key in ('lost_units', 'lost_margin', 'avg_pallets', 'peak_pallets',
                                                 'days_over_capacity', 'stockout_sku_days', 'ending_on_hand', 'ordered_cases'))


def test_missing_demand_days_stay_aligned(played_week, monkeypatch):
    original_read = play.read_sql

    def read(query, **params):
        frame = original_read(query, **params)
        if 'FROM store_orders' in query:
            return frame[frame.date != START + timedelta(days=2)].copy()
        return frame

    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    assert len(result['dates']) == len(result['demand']) == 7
    assert result['demand'][2] == [0., 0.]
    for policy in ('scoop', 'baseline'):
        run = result['runs'][policy]
        assert run['daily'][2]['demand'] == 0
        assert len(run['per_sku']['lost']) == 7


def test_expected_evidence_keeps_missing_cells_unknown(played_week, monkeypatch):
    original_read = play.read_sql

    def read(query, **params):
        if 'FROM model_runs' in query:
            return pd.DataFrame({'id': ['issued'], 'trained_through': [START - timedelta(days=1)]})
        if 'FROM daily_expectations' in query:
            assert params == {'r': 'issued', 'a': START, 'b': START + timedelta(days=6)}
            return pd.DataFrame({'date': [START, START + timedelta(days=1)],
                                 'sku': ['A', 'B'], 'expected_units': [2.5, 1.25]})
        return original_read(query, **params)

    monkeypatch.setattr(play, 'read_sql', read)
    result = play.simulate('test-plan', START, days=7)
    assert result['expected_source'] == {'run_id': 'issued', 'trained_through': str(START - timedelta(days=1))}
    assert result['expected'][0] == [2.5, None]
    assert result['expected'][1] == [None, 1.25]
    assert all(value is None for row in result['expected'][2:] for value in row)


def test_events_reference_orders_and_match_arrival_quantities(played_week):
    result = played_week
    orders = [event for event in result['events'] if event['kind'] == 'order']
    assert {(event['date'], line['sku'], line['cases']) for event in orders for line in event['lines']} == {
        (START.isoformat(), 'A', 1), ((START + timedelta(days=1)).isoformat(), 'B', 2)}
    arrivals = [event for event in result['events'] if event['kind'] == 'arrival']
    assert {(event['date'], event['sku'], event['cases']) for event in arrivals if event['cases']} == {
        ((START + timedelta(days=3)).isoformat(), 'A', 1),
        ((START + timedelta(days=4)).isoformat(), 'B', 2)}
    assert any(event['date'] == START.isoformat() and event['sku'] == 'B' for event in arrivals)
    assert all(event['order_dates'] and event['card_ids'] == [] for event in arrivals if event['cases'])
    for event in result['events']:
        if event['kind'] == 'stockout':
            assert 'order_dates' in event and 'card_ids' in event


def test_whole_and_affected_summaries_derive_from_daily_sku_rows(played_week):
    result = played_week
    for policy in ('scoop', 'baseline'):
        run = result['runs'][policy]
        rows = run['per_sku']
        whole = result['summary'][policy]
        affected = result['affected_summary'][policy]
        for day, daily in enumerate(run['daily']):
            assert daily['demand'] == pytest.approx(sum(result['demand'][day]))
            assert daily['shipped'] == pytest.approx(sum(rows['shipped'][day]))
            assert daily['lost'] == pytest.approx(sum(rows['lost'][day]))
            assert daily['arrived_units'] == pytest.approx(sum(rows['arrived'][day]))
            assert daily['on_hand'] == pytest.approx(sum(rows['on_hand'][day]))
        assert whole['lost_units'] == pytest.approx(sum(map(sum, rows['lost'])))
        assert whole['ending_on_hand'] == pytest.approx(sum(rows['on_hand'][-1]))
        assert whole['ordered_cases'] == sum(map(sum, rows['placed_cases']))
        assert whole['stockout_sku_days'] == sum(value > 0 for row in rows['lost'] for value in row)
        assert affected == whole
    assert result['affected_comparison']['units_saved'] == pytest.approx(
        result['affected_summary']['baseline']['lost_units'] - result['affected_summary']['scoop']['lost_units'])
