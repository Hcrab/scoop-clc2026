"""Deterministic forward calibration fixtures: no providers or database writes."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scoop import planning
from scoop.algorithms import forecast, protection_calibration as calibration, replenish, runs


AS_OF = date(2026, 7, 13)


def calibrated(values):
    return calibration.ProtectionCalibration(np.asarray(values), pd.DataFrame(), {"method": "fixture"})


@pytest.mark.parametrize("q, expected", [
    (0., .3), (.1, .3), (.25, .6), (.5, 1.35), (.75, 2.1), (.9, 2.4), (1., 2.4),
])
def test_finite_ranks_and_empirical_median(q, expected):
    scores = calibrated(np.arange(1, 9) * .3)
    assert scores.quantile(q) == pytest.approx(expected)
    assert calibrated([1.2]).quantile(q) == 1.2


@pytest.mark.parametrize("values", [[], [np.nan], [np.inf], [-1], [[1, 2]]])
def test_invalid_calibration_cannot_fabricate_service_levels(values):
    with pytest.raises(ValueError, match="forward scores"):
        calibrated(values)


def test_uncertainty_uses_same_finite_rank_probabilities_and_recenters():
    scores = calibrated(np.arange(1, 9) * .3)
    qs = [.1, .5, .9, .75]
    actual = replenish._uncertain_ratio_quantiles(scores, .16, qs)
    expected = replenish._uncertain_ratio_quantiles(scores.values, .16, [scores.probability(q) for q in qs])
    np.testing.assert_allclose(actual, expected)
    assert actual[1] == pytest.approx(np.median(scores.values))
    plain = replenish._uncertain_ratio_quantiles(scores.values, 0., qs)
    np.testing.assert_allclose(plain, np.quantile(scores.values, qs))
    assert actual[0] < actual[1] < actual[2]


def forward_fixture(monkeypatch):
    forecast._PROTECTION_CACHE.clear()
    forecast._DAILY_MEAN_CACHE.clear()
    calibration._RECENT_CACHE.clear()
    products = pd.DataFrame({
        "sku": ["A", "B", "C"], "lead_time_days": [2, 1, 1], "review_days": [3, 1, 1],
        "order_weekday": [0, 2, 6], "price_hkd": [10.] * 3, "cost_hkd": [6.] * 3,
        "units_per_case": [10] * 3, "cases_per_pallet": [10] * 3, "moq_cases": [3] * 3,
    })
    static = SimpleNamespace(products=products, stores=pd.DataFrame({"store_id": ["S1", "S2"]}))
    dates = pd.date_range("2026-05-01", "2026-08-31")
    actual = pd.MultiIndex.from_product([dates, products.sku], names=["date", "sku"]).to_frame(index=False)
    actual["units"] = actual.sku.map({"A": 40., "B": 10., "C": 0.})
    actual["stores"] = 2
    calls = {"queries": [], "models": [], "weather": []}

    def sql(query, **kwargs):
        calls["queries"].append((query, kwargs))
        # Return even poisoned future data: the calibration boundary must still hold.
        return actual.copy()

    def weather(st, issued, targets):
        calls["weather"].append(issued)
        return pd.DataFrame({"date": targets, "tmax": 25., "rain_mm": 0.})

    def features(st, targets, weather):
        assert set(weather.date) == set(targets)
        return pd.MultiIndex.from_product([targets, st.stores.store_id, st.products.sku],
                                         names=["date", "store_id", "sku"]).to_frame(index=False)

    class Model:
        def __init__(self, effective):
            self.version = effective.isoformat()
            self.trained_through = effective - timedelta(days=1)

        def predict(self, frame, mean_only=False):
            assert mean_only
            # Deliberately different monthly forecasts to detect wrong model selection.
            return frame.assign(mean=np.where(frame.sku == "C", 0., float(self.trained_through.month)))

    def monthly(effective, st):
        calls["models"].append(effective)
        return Model(effective.replace(day=1))

    monkeypatch.setattr(forecast, "read_sql", sql)
    monkeypatch.setattr(forecast, "forecast_weather", weather)
    monkeypatch.setattr(forecast, "build_features", features)
    monkeypatch.setattr(runs, "monthly_model", monthly)
    monkeypatch.setattr(calibration, "get_setting", lambda *args: "42")
    return static, actual, calls, monthly


def test_recent_monthly_selection_calendar_windows_and_cutoffs(monkeypatch):
    static, actual, calls, _ = forward_fixture(monkeypatch)
    result = calibration.recent_forward_calibration(static, AS_OF)
    scores = result.scores
    assert calls["models"] == [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)]
    for row in scores.itertuples():
        effective = (row.issued + timedelta(days=1)).replace(day=1)
        assert row.source_model_version == effective.isoformat()
        assert row.trained_through == effective - timedelta(days=1) <= row.issued
        assert row.issued.weekday() == 6
        assert AS_OF - timedelta(days=56) <= row.issued < AS_OF
        assert row.outcome_end.date() < AS_OF
    # May 31's next-day operational model is June, trained through May 31.
    assert set(scores.loc[scores.issued == date(2026, 5, 31), "source_model_version"]) == {"2026-06-01"}
    jul5 = scores[scores.issued == date(2026, 7, 5)].set_index("sku")
    assert set(jul5.index) == {"A", "B"}  # C ends July 13, so it is incomplete.
    assert jul5.loc["A", "pdays"] == 5
    assert jul5.loc["B", "pdays"] == 4  # two days waiting for Wednesday + L/R.
    assert jul5.loc["A", "actual"] == 200.
    assert jul5.loc["B", "actual"] == 40.
    assert jul5.loc["A", "forecast"] == 5 * 2 * 6
    assert scores.loc[scores.sku == "C", "pdays"].eq(8).all()
    assert date(2026, 7, 12) not in set(scores.issued)
    assert scores.loc[scores.sku == "C", "ratio"].eq(0.).all()
    assert result.values.min() == .3 and result.values.max() == 3.
    assert result.metadata["sample_count"] == len(scores)
    assert result.metadata["method"] == calibration.METHOD
    assert result.metadata["actuals_cutoff"] == "2026-07-12"
    assert result.metadata["outcome_end"] < "2026-07-13"
    assert all(kwargs["b"] <= AS_OF - timedelta(days=1) for _, kwargs in calls["queries"])
    assert set(scores.issued) <= set(calls["weather"])
    count = len(calls["queries"])
    assert calibration.recent_forward_calibration(static, AS_OF) is result
    assert len(calls["queries"]) == count
    monkeypatch.setattr(calibration, "get_setting", lambda *args: "43")
    assert calibration.recent_forward_calibration(static, AS_OF).metadata["seed"] == "43"
    assert len(calls["queries"]) > count


def test_future_poison_labels_do_not_change_calibration_without_cache(monkeypatch):
    static, actual, calls, _ = forward_fixture(monkeypatch)
    before = calibration.recent_forward_calibration(static, AS_OF)
    actual.loc[actual.date >= pd.Timestamp(AS_OF), "units"] = 999999999.
    calibration._RECENT_CACHE.clear()
    after = calibration.recent_forward_calibration(static, AS_OF)
    pd.testing.assert_frame_equal(before.scores, after.scores)
    np.testing.assert_array_equal(before.values, after.values)
    assert all(kwargs["b"] < AS_OF for _, kwargs in calls["queries"])


def test_missing_days_or_store_rows_exclude_windows_instead_of_zero_filling(monkeypatch):
    static, actual, _, _ = forward_fixture(monkeypatch)
    before = calibration.recent_forward_calibration(static, AS_OF)
    actual.drop(actual.index[(actual.date == "2026-06-16") & (actual.sku == "B")], inplace=True)
    actual.loc[(actual.date == "2026-06-17") & (actual.sku == "A"), "stores"] = 1
    calibration._RECENT_CACHE.clear()
    after = calibration.recent_forward_calibration(static, AS_OF)
    assert len(after.scores) == len(before.scores) - 2
    affected = after.scores[after.scores.issued == date(2026, 6, 14)]
    assert set(affected.sku) == {"C"}


def test_calibration_rejects_training_overlap_before_reading_actuals(monkeypatch):
    static, _, calls, _ = forward_fixture(monkeypatch)
    model = SimpleNamespace(trained_through=date(2026, 6, 2))
    with pytest.raises(ValueError, match="training cutoff"):
        forecast.calibrate_ratios(model, static, [date(2026, 5, 31)], as_of=AS_OF, order_calendar=True)
    assert not calls["queries"]


def test_zero_forecast_uses_unit_denominator_and_empty_history_is_explicit(monkeypatch):
    static, actual, _, _ = forward_fixture(monkeypatch)
    actual.loc[actual.sku == "C", "units"] = .125
    result = calibration.recent_forward_calibration(static, AS_OF)
    zero_mean = result.scores[result.scores.sku == "C"]
    assert zero_mean.forecast.eq(0.).all()
    assert zero_mean.actual.eq(1.).all()
    assert zero_mean.ratio.eq(1.).all()
    actual.drop(actual.index, inplace=True)
    calibration._RECENT_CACHE.clear()
    with pytest.raises(ValueError, match="No fully observed"):
        calibration.recent_forward_calibration(static, AS_OF)


def test_normal_planning_uses_recent_quantiles_for_targets_and_intervals(monkeypatch):
    static, _, _, monthly = forward_fixture(monkeypatch)
    model = monthly(date(2026, 7, 1), static)
    # Historical arrays are poisoned to prove suggestions use the recent calibration.
    old = SimpleNamespace(model=model, ratio_values=np.array([999.]), metadata={})
    monkeypatch.setattr(planning, "artifacts", lambda: SimpleNamespace(static=static, run_for=lambda _: old))
    monkeypatch.setattr(planning, "read_sql", lambda *a, **k: pd.DataFrame({"capacity_pallets": [100.]}))
    monkeypatch.setattr(planning, "capacity_projection", lambda *a, **k:
                        (np.zeros((3, 3)), np.ones((3, 3), dtype=bool)))
    position = pd.DataFrame({"sku": ["A", "B", "C"], "on_hand_units": [0] * 3, "on_order": [0] * 3})
    cohort = {"sku_factors": {"A": {"f50": 1.25, "s2": 0.}}}
    result = planning.suggest_orders(AS_OF, [], service_level=.75, position=position,
                                     overrides=[], cohort_result=cohort)
    recent = calibration.recent_forward_calibration(static, AS_OF)
    row = result.set_index("sku").loc["A"]
    mean = 5 * 2 * 6 * 1.25
    assert row.target_units == pytest.approx(mean * recent.quantile(.75))
    assert row.demand_p10 == pytest.approx(mean * recent.quantile(.1))
    assert row.demand_p50 == pytest.approx(mean * recent.quantile(.5))
    assert row.demand_p90 == pytest.approx(mean * recent.quantile(.9))
    assert row.final_cases == max(3, int(np.ceil(row.target_units / 10)))
    assert result.set_index("sku").loc["C", "target_units"] == 0.
    assert result.set_index("sku").loc["C", "final_cases"] == 0
    assert result.attrs["protection_calibration"] == recent.metadata
    assert result.attrs["cohort_model"] == cohort
    assert row.adjustment == 1.25 and row.trained_through == date(2026, 6, 30)
    lower = planning.suggest_orders(AS_OF, [], service_level=.5, position=position,
                                    overrides=[], cohort_result=cohort)
    assert lower.set_index("sku").loc["A", "target_units"] <= row.target_units
