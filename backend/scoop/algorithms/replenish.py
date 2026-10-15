"""Order-up-to replenishment with a newsvendor critical ratio and a cold-store capacity limit.

For each SKU, on its supplier's order day:

    protection period   P = lead time L + review period R
    demand over P       D ~ forecast mean x empirical actual/forecast ratio
    critical ratio      CR = Cu / (Cu + Co)
                        Cu = margin lost per unit short, Co = cost of holding one unit too many
    target level        S = quantile of D at CR
    inventory position  IP = on hand + on order
    order               max(0, S - IP), rounded up to cases, at least the supplier MOQ

If the projected cold-store pallets exceed capacity, cases are removed one at a time from the
SKU whose last case has the lowest marginal value

    MV = Cu x P(D > S) - Co x P(D <= S)

This is a marginal-value-per-pallet heuristic, not a global optimum with differing footprints and MOQs.
Dated projections check each arrival separately; without a supplied projection, capacity
conservatively counts all existing inventory/pipeline plus new cases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

HOLDING_RATE = 0.025  # per cycle: 1% storage/financing + 1.5% summer carryover/markdown provision
CR_BOUNDS = (0.5, 0.98)


@dataclass
class SkuInput:
    sku: str
    mean: float  # forecast demand over the protection period, already adjusted for trends
    pdays: int
    price: float
    cost: float
    units_per_case: int
    cases_per_pallet: int
    moq_cases: int
    on_hand: int
    on_order: int
    lead_days: int
    adjustment: float = 1.0
    factor_log_variance: float = 0.0


def critical_ratio(price: float, cost: float, service_level: float | None = None) -> float:
    if service_level is not None:
        return float(np.clip(service_level, *CR_BOUNDS))
    cu = price - cost
    co = HOLDING_RATE * cost
    return float(np.clip(cu / (cu + co), *CR_BOUNDS))


def _ratio_quantile(ratios: np.ndarray, q: float) -> float:
    return float(np.quantile(ratios, q))


def _uncertain_ratio_quantiles(ratios: np.ndarray, variance: float, probabilities):
    """Deterministic quadrature for empirical ratio × lognormal factor error.

    Hermite nodes integrate the N(0, variance) log effect. The weighted mixture
    is recentered to the empirical median, because ``mean`` already includes
    f50. Node count controls numerical accuracy, not demand risk or safety stock.
    """
    if variance <= 0:
        return [_ratio_quantile(ratios, q) for q in probabilities]
    nodes, weights = np.polynomial.hermite.hermgauss(41)
    factors = np.exp(np.sqrt(2 * variance) * nodes)
    values = (np.asarray(ratios, dtype=float)[:, None] * factors[None, :]).ravel()
    masses = np.broadcast_to(weights / (np.sqrt(np.pi) * len(ratios)),
                             (len(ratios), len(nodes))).ravel()
    order = np.argsort(values)
    values, masses = values[order], masses[order]
    cumulative = np.cumsum(masses)
    quantiles = np.interp(probabilities + [0.5], cumulative, values)
    center = _ratio_quantile(ratios, .5) / quantiles[-1] if quantiles[-1] > 0 else 1.
    return [float(q * center) for q in quantiles[:-1]]


def plan_orders(items: list[SkuInput], ratios: np.ndarray, capacity_pallets: float, service_level: float | None = None, capacity_baseline: np.ndarray | None = None,
                arrival_mask: np.ndarray | None = None,
                initial_cases: dict[str, int] | None = None) -> pd.DataFrame:
    rows = []
    for it in items:
        cr = critical_ratio(it.price, it.cost, service_level)
        if it.factor_log_variance < 0 or not np.isfinite(it.factor_log_variance):
            raise ValueError("factor_log_variance must be finite and nonnegative")
        q10, q50, q90, qcr = _uncertain_ratio_quantiles(
            ratios, it.factor_log_variance, [.1, .5, .9, cr])
        target = it.mean * qcr
        position = it.on_hand + it.on_order
        need = max(0.0, target - position)
        cases = math.ceil(need / it.units_per_case) if need > 0 else 0
        if cases:
            cases = max(cases, it.moq_cases)
        if initial_cases is not None:
            cases = initial_cases.get(it.sku, 0)
        rows.append({
            "sku": it.sku,
            "pdays": it.pdays,
            "demand_p10": it.mean * q10,
            "demand_p50": it.mean * q50,
            "demand_p90": it.mean * q90,
            "adjustment": it.adjustment,
            "critical_ratio": cr,
            "excess_unit_cost_rate": HOLDING_RATE,
            "excess_unit_cost_basis": "Per cycle: 1% storage/financing + 1.5% summer carryover/markdown provision, applied to unit cost.",
            "target_units": target,
            "on_hand_units": it.on_hand,
            "on_order_units": it.on_order,
            "inventory_position": position,
            "suggested_cases": cases,
            "capacity_cut_cases": 0,
            "_mu": it.mean * q50,
            "_sigma": max(it.mean * (q90 - q10) / 2.563, 1.0),
            "_cu": it.price - it.cost,
            "_co": HOLDING_RATE * it.cost,
            "_upc": it.units_per_case,
            "_upp": it.units_per_case * it.cases_per_pallet,
            "_lead_mean": it.mean / max(it.pdays, 1) * it.lead_days,
        })
    plan = pd.DataFrame(rows)
    if plan.empty:
        return plan

    def projected_pallets(df: pd.DataFrame) -> float:
        # stock right after the order arrives: position + order - demand during the lead time
        peak = (df.inventory_position + (df.suggested_cases - df.capacity_cut_cases) * df._upc).clip(lower=0)
        return float((peak / df._upp).sum())

    moq = {it.sku: it.moq_cases for it in items}
    inherited = float((plan.inventory_position.clip(lower=0) / plan._upp).sum())
    moqs = plan.sku.map(moq).to_numpy()
    keep = plan.suggested_cases.to_numpy(dtype=int).copy()
    position = plan.inventory_position.to_numpy()
    upc, upp = plan._upc.to_numpy(), plan._upp.to_numpy()
    mu, sigma = plan._mu.to_numpy(), plan._sigma.to_numpy()
    cu, co = plan._cu.to_numpy(), plan._co.to_numpy()
    footprint = upc / upp
    def occupancy(cases):
        if capacity_baseline is None:
            return np.array([inherited + float(cases @ footprint)])
        return (np.maximum(capacity_baseline + arrival_mask*(cases*upc)[None,:], 0)/upp[None,:]).sum(axis=1)
    baseline_peaks = occupancy(np.zeros_like(keep))
    limits = np.maximum(capacity_pallets, baseline_peaks)
    while (occupancy(keep) > limits + 1e-10).any() and (keep > 0).any():
        level = position + keep * upc
        p_short = 1 - norm.cdf(level, loc=mu, scale=sigma)
        value = (cu*p_short - co*(1-p_short))*upp
        if arrival_mask is not None:
            violated = occupancy(keep) > limits + 1e-10
            value[~arrival_mask[violated].any(axis=0)] = np.inf
        value[keep <= 0] = np.inf
        i = int(np.argmin(value))
        cut = 1 if keep[i] > moqs[i] else int(keep[i])
        keep[i] -= cut

    plan["capacity_cut_cases"] = plan.suggested_cases.to_numpy()-keep
    plan["inherited_overcapacity_pallets"] = max(0., float(baseline_peaks.max())-capacity_pallets)
    plan["projected_pallets"] = float(occupancy(keep).max())
    plan["final_cases"] = plan.suggested_cases - plan.capacity_cut_cases
    return plan.drop(columns=[c for c in plan.columns if c.startswith("_")])
