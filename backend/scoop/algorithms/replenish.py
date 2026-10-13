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

HOLDING_RATE = 0.25  # cost of one excess unit per cycle, as a share of unit cost (storage + markdown risk)
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


def critical_ratio(price: float, cost: float, service_level: float | None = None) -> float:
    if service_level is not None:
        return float(np.clip(service_level, *CR_BOUNDS))
    cu = price - cost
    co = HOLDING_RATE * cost
    return float(np.clip(cu / (cu + co), *CR_BOUNDS))


def _ratio_quantile(ratios: np.ndarray, q: float) -> float:
    return float(np.quantile(ratios, q))


def plan_orders(items: list[SkuInput], ratios: np.ndarray, capacity_pallets: float, service_level: float | None = None, capacity_baseline: np.ndarray | None = None,
                arrival_mask: np.ndarray | None = None) -> pd.DataFrame:
    r_med = _ratio_quantile(ratios, 0.5)
    r_sigma = (_ratio_quantile(ratios, 0.9) - _ratio_quantile(ratios, 0.1)) / 2.563
    rows = []
    for it in items:
        cr = critical_ratio(it.price, it.cost, service_level)
        target = it.mean * _ratio_quantile(ratios, cr)
        position = it.on_hand + it.on_order
        need = max(0.0, target - position)
        cases = math.ceil(need / it.units_per_case) if need > 0 else 0
        if cases:
            cases = max(cases, it.moq_cases)
        rows.append({
            "sku": it.sku,
            "pdays": it.pdays,
            "demand_p10": it.mean * _ratio_quantile(ratios, 0.1),
            "demand_p50": it.mean * r_med,
            "demand_p90": it.mean * _ratio_quantile(ratios, 0.9),
            "adjustment": it.adjustment,
            "critical_ratio": cr,
            "target_units": target,
            "on_hand_units": it.on_hand,
            "on_order_units": it.on_order,
            "inventory_position": position,
            "suggested_cases": cases,
            "capacity_cut_cases": 0,
            "_mu": it.mean * r_med,
            "_sigma": max(it.mean * r_sigma, 1.0),
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
