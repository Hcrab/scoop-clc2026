"""Apply planner context to fresh cohort posteriors, without changing the fit."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import timedelta
from math import exp, log1p, sqrt

import numpy as np
import pandas as pd
from scipy.stats import norm

from .cohort_model import Z80

PRIOR_SD = {"low": .30, "medium": .15, "high": .07}


def _truncated(mean, variance, ceiling):
    """Moments of N(mean, variance) conditioned on X <= ceiling."""
    if variance <= 0:
        return min(mean, ceiling), 0.
    sd = sqrt(variance)
    a = (ceiling - mean) / sd
    log_ratio = norm.logpdf(a) - norm.logcdf(a)
    ratio = exp(log_ratio)
    return mean - sd * ratio, max(0., variance * (1 - a * ratio - ratio * ratio))


def _members(override, groups):
    catalog = groups if isinstance(groups, dict) else {g.id: g for g in groups}
    path = override.get("tag_path") or []
    conditions = []
    district_conditions = []
    for step in path:
        if step['id'].startswith('district:'):
            district_conditions.append((step['id'].split(':', 1)[1], bool(step['included'])))
            continue
        group = catalog.get(step["id"])
        if group is None:
            raise ValueError(f"Unknown group: {step['id']}")
        conditions.append((set(getattr(group, "skus", group)), bool(step["included"])))
    districts = set(override.get("districts") or [])
    return lambda u: (not districts or u["district"] in districts) and all((u["district"] == district) == included for district, included in district_conditions) and all(
        (u["sku"] in members) == included for members, included in conditions)


def apply_overrides(result, overrides, products, as_of, groups):
    """Return an independent fit result with one recomputed factor per SKU.

    A saved tag path is evaluated against current unit membership, not leaf IDs.
    District conditional errors remain independent; units sharing a leaf retain
    the shared leaf variance until nonlinear cap truncation, for which covariance
    is omitted as an explicit approximation (the marginal truncated variances remain exact).
    """
    out = deepcopy(result)
    units = out.get("units", [])
    leaves = {leaf["id"]: leaf for leaf in out.get("leaves", [])}
    as_of = pd.Timestamp(as_of).date()
    product_rows = products.set_index("sku")
    state = []
    for u in units:
        leaf = leaves[u["leaf_id"]]
        shared = float(leaf["posterior_variance"])
        state.append({"conditional": float(u.get("conditional_variance", max(0., u["s2"] - shared))),
                      "shared": shared, "key": u["leaf_id"], "scale": 1., "cap": None})
    metadata = []
    cases = {}
    for override in overrides:
        kind = override["type"]
        if kind == "cases":
            value = override["value"]
            sku, count = value["sku"], int(value["cases"])
            if count < 0:
                raise ValueError("Cases must be nonnegative")
            cases[sku] = count
            metadata.append({"id": override.get("id"), "type": kind, "matched_units": [], "sku": sku, "cases": count})
            continue
        predicate = _members(override, groups)
        indices = [i for i, u in enumerate(units) if predicate(u)]
        trace = {"id": override.get("id"), "type": kind,
                 "matched_units": [{"sku": units[i]["sku"], "district": units[i]["district"]} for i in indices]}
        if kind == "one_off":
            for i in indices:
                units[i]["m"] = units[i]["s2"] = 0.
                state[i].update(conditional=0., shared=0., key=None)
        elif kind == "ends_on":
            end = pd.Timestamp(override["value"]).date()
            dates = {}
            for i in indices:
                u = units[i]
                p = product_rows.loc[u["sku"]]
                order = as_of + timedelta(days=(int(p.order_weekday) - as_of.weekday()) % 7)
                start = order + timedelta(days=int(p.lead_time_days))
                finish = start + timedelta(days=int(p.review_days))
                days = max(0, min((end - start).days, (finish - start).days))
                fraction = days / max((finish - start).days, 1)
                factor = exp(u['m'])
                blended = 1 + fraction * (factor - 1)
                derivative = fraction * factor / blended
                u['m'] = log1p(fraction * (factor - 1))
                u['s2'] *= derivative * derivative
                state[i]['conditional'] *= derivative * derivative
                state[i]['shared'] *= derivative * derivative
                state[i]['scale'] *= derivative
                dates[u["sku"]] = {"order_date": order.isoformat(), "cover_start": start.isoformat(),
                                    "cover_end_exclusive": finish.isoformat(), "ends_on": end.isoformat(),
                                    "fraction": fraction}
            trace["cover"] = dates
            trace['uncertainty'] = 'arithmetic day-weighted factor; delta-method log variance' 
        elif kind == "cap":
            ceiling = log1p(float(override["value"]))
            for i in indices:
                u = units[i]
                u["m"], u["s2"] = _truncated(u["m"], u["s2"], ceiling)
                state[i].update(conditional=u["s2"], shared=0., key=None, cap=ceiling)
            trace["log_ceiling"] = ceiling
        elif kind == "expect":
            value = override["value"]
            prior_mean = log1p(float(value["pct"]))
            prior_var = PRIOR_SD[value["strength"]] ** 2
            # Update each targeted leaf once. The prior is shared cohort evidence,
            # never repeated independently for every district observation.
            for leaf_id in {units[i]["leaf_id"] for i in indices}:
                leaf = leaves[leaf_id]
                old_mean, old_var = leaf["posterior_mean"], leaf["posterior_variance"]
                data_mean = leaf.get('raw_estimate', old_mean)
                data_var = leaf.get('variance', old_var)
                new_var = 1 / (1 / data_var + 1 / prior_var) if data_var > 0 else 0.
                new_mean = new_var * (data_mean / data_var + prior_mean / prior_var) if data_var > 0 else data_mean
                leaf["posterior_mean"], leaf["posterior_variance"] = new_mean, new_var
                leaf["interval_80"] = [new_mean - Z80 * sqrt(new_var), new_mean + Z80 * sqrt(new_var)]
                for i in indices:
                    u = units[i]
                    if u["leaf_id"] != leaf_id:
                        continue
                    weight = float(u.get("leaf_weight", 1.)) * state[i]["scale"]
                    u["m"] += weight * (new_mean - old_mean)
                    state[i]["shared"] = state[i]["scale"] ** 2 * new_var
                    u["s2"] = state[i]["conditional"] + state[i]["shared"]
            trace["prior_mean"] = prior_mean
            trace["prior_sd"] = sqrt(prior_var)
        else:
            raise ValueError(f"Unknown override type: {kind}")
        metadata.append(trace)

    by_sku = defaultdict(list)
    for i, u in enumerate(units):
        by_sku[u["sku"]].append(i)
    factors = deepcopy(out.get("sku_factors", {}))
    for sku, indices in by_sku.items():
        demand = np.array([float(units[i].get("expected_recent", units[i].get("E_r", 0))) for i in indices])
        weights = demand / demand.sum() if demand.sum() > 0 else np.full(len(indices), 1 / len(indices))
        mean = float(sum(w * units[i]["m"] for w, i in zip(weights, indices)))
        variance = float(sum(w * w * state[i]["conditional"] for w, i in zip(weights, indices)))
        for key in {state[i]["key"] for i in indices if state[i]["key"] is not None}:
            # Shared leaf perturbation has unit-specific coefficients after an
            # ends_on fraction or an expectation update.
            variance += float(sum(w * sqrt(state[i]["shared"])
                                  for w, i in zip(weights, indices) if state[i]["key"] == key)) ** 2
        sd = sqrt(max(variance, 0.))
        f90_log = mean + Z80 * sd
        caps = [state[i]["cap"] for i in indices]
        if caps and all(c is not None for c in caps):
            f90_log = min(f90_log, max(caps))
        factors[sku] = {"f10": exp(mean - Z80 * sd), "f50": exp(mean),
                        "f90": exp(f90_log), "m": mean, "s2": variance}
    out["sku_factors"] = factors
    out["cases_overrides"] = cases
    out["applied_overrides"] = metadata
    out.setdefault("method", {})["override_covariance"] = (
        "Shared leaf covariance retained for linear one_off/ends_on/expect updates; "
        "capped marginal posteriors use exact truncated moments and zero cross-district covariance")
    return out
