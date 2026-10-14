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
            {"sku": "A", "name": "A", "brand": "Test", "price_hkd": 4.0,
             "cost_hkd": 2.0, "units_per_case": 10, "cases_per_pallet": 10,
             "moq_cases": 1, "lead_time_days": 3, "order_weekday": 0, "review_days": 7},
            {"sku": "B", "name": "B", "brand": "Test", "price_hkd": 3.0,
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
