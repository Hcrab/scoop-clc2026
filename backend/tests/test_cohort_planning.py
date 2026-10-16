"""The one cohort factor used by replenishment and its capacity check."""

from datetime import date
from types import SimpleNamespace
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest

from scoop import planning
from scoop.algorithms.protection_calibration import ProtectionCalibration


DAY = date(2026, 7, 13)


def _fixtures(monkeypatch):
    products = pd.DataFrame([{"sku": "A", "order_weekday": 0, "price_hkd": 4.0,
                              "cost_hkd": 2.0, "units_per_case": 10,
                              "cases_per_pallet": 10, "moq_cases": 1, "lead_time_days": 2}])
    static = SimpleNamespace(products=products)
    model = SimpleNamespace(version="test", trained_through=DAY)
    monthly = SimpleNamespace(model=model, ratio_values={}, metadata={})
    monkeypatch.setattr(planning, "recent_forward_calibration", lambda *args:
                        ProtectionCalibration(np.linspace(.8, 1.2, 101), pd.DataFrame(), {"method": "fixture"}))
    monkeypatch.setattr(planning, "artifacts", lambda: SimpleNamespace(
        static=static, run_for=lambda day: monthly))
    monkeypatch.setattr(planning, "inventory_position", lambda day: pd.DataFrame(
        [{"sku": "A", "on_hand_units": 4, "on_order": 3}]))
    monkeypatch.setattr(planning, "read_sql", lambda *args, **kwargs: pd.DataFrame(
        {"capacity_pallets": [10.0]}))
    monkeypatch.setattr(planning, "sku_adjustments", lambda *args: pytest.fail(
        "legacy directions must not affect cohort orders"))
    return static, model


def test_suggestion_applies_one_cohort_factor_to_mean_and_capacity(monkeypatch):
    _fixtures(monkeypatch)
    monkeypatch.setattr(planning, "protection_forecast", lambda *args, **kwargs: (
        pd.DataFrame([{"sku": "A", "mean": 100.0, "pdays": 9}]), pd.DataFrame()))
    seen = {}

    def capacity(*args, **kwargs):
        seen["capacity_factor"] = args[4]["A"]
        return np.zeros((3, 1)), np.ones((3, 1), dtype=bool)

    def replenish(items, *args, **kwargs):
        seen["item"] = items[0]
        return pd.DataFrame([{"sku": "A"}])

    monkeypatch.setattr(planning, "capacity_projection", capacity)
    monkeypatch.setattr(planning, "plan_orders", replenish)
    result = planning.suggest_orders(
        DAY, [{"bucket": "more", "tag_id": "overlap", "factor": 1.6,
               "districts": ["all"]}] * 2,
        cohort_result={"sku_factors": {"A": {"f50": 1.25}}})
    assert result.attrs["cohort_model"]["sku_factors"]["A"]["f50"] == 1.25
    assert seen["item"].mean == pytest.approx(125.0)
    assert seen["item"].adjustment == pytest.approx(1.25)
    assert seen["capacity_factor"] == pytest.approx(1.25)


def test_confirmation_capacity_refits_and_uses_same_cohort_factor(monkeypatch):
    _fixtures(monkeypatch)
    fitted = []
    monkeypatch.setattr(planning.cohort_model, "fit", lambda plan: (
        fitted.append(plan.week_start) or {"sku_factors": {"A": {"f50": 1.25}}}))
    seen = {}

    def capacity(*args, **kwargs):
        seen["factor"] = args[4]["A"]
        return np.zeros((3, 1)), np.ones((3, 1), dtype=bool)

    monkeypatch.setattr(planning, "capacity_projection", capacity)
    result = planning.confirmation_capacity(DAY, {"A": 1})
    assert fitted == [DAY]
    assert seen["factor"] == pytest.approx(1.25)
    assert result["feasible"] is True


def test_saved_capacity_factors_preserve_projection_without_refit_or_double_context(monkeypatch):
    _fixtures(monkeypatch)
    monkeypatch.setattr(planning.cohort_model, "fit", lambda _: {"sku_factors": {"A": {"f50": 1.25}}})
    monkeypatch.setattr(planning, "capacity_projection", lambda *args, **kwargs:
                        (np.full((3, 1), args[4]["A"] * 20), np.ones((3, 1), dtype=bool)))
    expected = planning.confirmation_capacity(DAY, {"A": 2})
    monkeypatch.setattr(planning.cohort_model, "fit", lambda _: pytest.fail("saved plan must not refit"))
    monkeypatch.setattr(planning, "contextual_effects", lambda *args: pytest.fail("saved factors already contain context"))
    actual = planning.confirmation_capacity(DAY, {"A": 2}, {"A": 1.25})
    assert actual == expected
    assert actual["projected_peak_pallets"] == pytest.approx(.45)


def test_recompute_refits_and_persists_new_cohort_evidence(monkeypatch):
    plan = SimpleNamespace(week_start=DAY, service_level=None, goal="margin",
                           summary={"existing": "kept"})
    added = []

    class Session:
        def get(self, model, key):
            return plan

        def execute(self, statement):
            return None

        def add(self, row):
            added.append(row)

    @contextmanager
    def scope():
        yield Session()

    monkeypatch.setattr(planning, "session_scope", scope)
    fresh = {"sku_factors": {"A": {"f50": 1.3}}, "leaves": [{"id": "fresh"}]}
    fit_dates = []
    monkeypatch.setattr(planning.cohort_model, "fit", lambda arg: (
        fit_dates.append(arg.week_start) or fresh))
    supplied = []
    rows = pd.DataFrame([{"sku": "A", "order_date": DAY, "pdays": 7,
                          "demand_p10": 8, "demand_p50": 10, "demand_p90": 12,
                          "adjustment": 1.3, "critical_ratio": .8, "target_units": 13,
                          "on_hand_units": 1, "on_order_units": 2,
                          "inventory_position": 3, "suggested_cases": 2,
                          "capacity_cut_cases": 0, "final_cases": 2}])

    def suggest(*args, **kwargs):
        supplied.append(kwargs["cohort_result"])
        return rows

    monkeypatch.setattr(planning, "suggest_orders", suggest)
    monkeypatch.setattr(planning, "read_sql", lambda *args, **kwargs: pd.DataFrame(
        {"sku": ["A"], "name": ["Product A"]}))
    planning.recompute_orders("plan")
    assert fit_dates == [DAY]
    assert supplied == [fresh]
    assert plan.summary == {"existing": "kept", "cohort_model": fresh}
    assert len(added) == 1 and added[0].adjustment == pytest.approx(1.3)


def test_direct_case_override_updates_projected_capacity(monkeypatch):
    _fixtures(monkeypatch)
    monkeypatch.setattr(planning, 'protection_forecast', lambda *args, **kwargs: (
        pd.DataFrame([{'sku':'A','mean':100.,'pdays':9}]), pd.DataFrame()))
    monkeypatch.setattr(planning, 'capacity_projection', lambda *args, **kwargs:
                        (np.zeros((3,1)), np.ones((3,1),dtype=bool)))
    monkeypatch.setattr(planning, 'plan_orders', lambda *args, **kwargs:
                        pd.DataFrame([{'sku':'A','final_cases':2,'projected_pallets':.2}]))
    result = planning.suggest_orders(DAY, [], overrides=[], cohort_result={
        'sku_factors':{'A':{'f50':1.}}, 'cases_overrides':{'A':5}})
    assert result.iloc[0].final_cases == 5
    assert result.iloc[0].projected_pallets == pytest.approx(.5)


@pytest.mark.parametrize('kind,value', [
    ('one_off', True), ('ends_on', '2026-07-17'), ('cap', .1),
    ('expect', {'pct': -.2, 'strength': 'high'}), ('cases', {'sku': 'A', 'cases': 3}),
])
def test_each_context_rule_reaches_actual_replenishment_orders(monkeypatch, kind, value):
    from test_cohort_overrides import fitted
    from scoop.ai import exploration_tools
    static, model = _fixtures(monkeypatch)
    static.products['review_days'] = 7
    monthly = SimpleNamespace(model=model, ratio_values=np.linspace(.8, 1.2, 101), metadata={})
    monkeypatch.setattr(planning, 'artifacts', lambda: SimpleNamespace(static=static, run_for=lambda _:monthly))
    monkeypatch.setattr(planning, 'protection_forecast', lambda *a, **k:
                        (pd.DataFrame([{'sku':'A','mean':100.,'pdays':9}]), pd.DataFrame()))
    monkeypatch.setattr(planning, 'capacity_projection', lambda *a, **k:
                        (np.zeros((3,1)), np.ones((3,1),dtype=bool)))
    @contextmanager
    def scope():
        yield None
    monkeypatch.setattr(planning, 'session_scope', scope)
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {})
    original = fitted()
    original['units'] = [u for u in original['units'] if u['sku']=='A']
    original['sku_factors'].pop('B')
    baseline = planning.suggest_orders(DAY, [], overrides=[], cohort_result=original)
    result = planning.suggest_orders(DAY, [], overrides=[{'type':kind,'value':value}], cohort_result=original)
    assert result.iloc[0].final_cases < baseline.iloc[0].final_cases
    if kind=='cases':
        assert result.iloc[0].final_cases == 3
        assert result.iloc[0].adjustment == pytest.approx(baseline.iloc[0].adjustment)
    elif kind=='one_off':
        assert result.iloc[0].adjustment == 1
    else:
        assert result.iloc[0].adjustment < baseline.iloc[0].adjustment
