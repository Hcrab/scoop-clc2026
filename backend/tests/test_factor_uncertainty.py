import numpy as np
import pytest

from scoop.algorithms.replenish import SkuInput, plan_orders


def item(sku="A", variance=0):
    return SkuInput(sku, 100, 14, 10, 6, 10, 10, 1, 0, 0, 2,
                    factor_log_variance=variance)


def test_zero_variance_preserves_empirical_quantiles_and_target():
    ratios = np.array([.8, .9, 1., 1.1, 1.2])
    result = plan_orders([item()], ratios, 100)
    row = result.iloc[0]
    assert row.demand_p10 == pytest.approx(100 * np.quantile(ratios, .1))
    assert row.demand_p50 == pytest.approx(100 * np.quantile(ratios, .5))
    assert row.demand_p90 == pytest.approx(100 * np.quantile(ratios, .9))
    assert row.target_units == pytest.approx(100 * np.quantile(ratios, row.critical_ratio))


def test_wider_factor_uncertainty_changes_quantiles_and_order():
    ratios = np.array([.8, .9, 1., 1.1, 1.2])
    base = plan_orders([item()], ratios, 100).iloc[0]
    wide = plan_orders([item(variance=.16)], ratios, 100).iloc[0]
    assert wide.demand_p10 < base.demand_p10
    assert wide.demand_p50 == pytest.approx(base.demand_p50)
    assert wide.demand_p90 > base.demand_p90
    assert wide.target_units > base.target_units
    assert wide.final_cases > base.final_cases


def test_capacity_cut_still_respects_limit_with_factor_uncertainty():
    result = plan_orders([item("A", .16), item("B", .16)],
                         np.array([.8, 1., 1.2]), .8)
    assert result.projected_pallets.max() <= .8
    assert result.final_cases.sum() < result.suggested_cases.sum()
