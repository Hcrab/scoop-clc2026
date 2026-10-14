"""Weekly plan: findings -> questions -> direction board -> purchase suggestions -> watch items.

This module joins the four algorithms and the investigator into one weekly cycle and
persists the result. The same functions run in the evaluation replay, so the numbers in the
report come from the code path the planner uses.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, select

from .ai import narrator
from .ai.investigator import investigate, review_near_misses
from .algorithms import cusum
from .algorithms.forecast import protection_forecast, build_features, forecast_weather, daily_mean
from .algorithms.replenish import SkuInput, plan_orders
from .algorithms.runs import RUN_B_END, artifacts, month_start, model_metadata
from .algorithms.shiftshare import decompose
from .db import engine, read_sql, session_scope
from .models import (
    Decision,
    DirectionItem,
    Finding,
    Hypothesis,
    Plan,
    PurchaseSuggestion,
    Question,
    WatchItem,
)
from .monitoring import monitoring

SIMILARITY = 0.6
MAX_FINDINGS = 6
FACTOR_BOUNDS = (0.6, 1.6)


# --------------------------------------------------------------------------- findings


def _excess_vectors(alarms: pd.DataFrame, as_of: pd.Timestamp) -> dict[tuple, pd.Series]:
    """Per alarm: excess units by SKU over its current run (actual - expected)."""
    m = monitoring()
    a = m.actual.assign(district=m.actual.store_id.map(m.store_district))
    e = m.expectations.assign(district=m.expectations.store_id.map(m.store_district))
    out = {}
    for r in alarms.itertuples():
        g = m.group_by_id[r.group]
        start = r.run_start
        aa = a[(a.date >= start) & (a.date <= as_of) & (a.district == r.district) & a.sku.isin(g.skus)]
        ee = e[(e.date >= start) & (e.date <= as_of) & (e.district == r.district) & e.sku.isin(g.skus)]
        v = aa.groupby("sku").ordered_units.sum().sub(ee.groupby("sku")["mean"].sum(), fill_value=0.0)
        out[(r.group, r.district, r.direction)] = v
    return out


def _cluster(alarms: pd.DataFrame, as_of: pd.Timestamp) -> list[dict]:
    """Merge alarms driven by the same SKUs; pick the tag that best explains each cluster."""
    m = monitoring()
    sig = alarms[alarms.significant].sort_values(["statistic", "group", "district", "direction"], ascending=[False, True, True, True])
    if sig.empty:
        return []
    vecs = _excess_vectors(sig, as_of)
    all_skus = list(m.group_by_id[sig.group.iloc[0]].skus)
    keys = list(vecs)
    skus = sorted(set().union(*[set(v.index) for v in vecs.values()]))
    mat = {k: vecs[k].reindex(skus, fill_value=0.0).to_numpy() for k in keys}
    used: set[tuple] = set()
    clusters = []
    for k in keys:
        if k in used:
            continue
        members = [k]
        used.add(k)
        for other in keys:
            if other in used or other[2] != k[2]:
                continue
            a, b = mat[k], mat[other]
            cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            if cos >= SIMILARITY:
                members.append(other)
                used.add(other)
        clusters.append(members)

    findings = []
    for members in clusters:
        direction = members[0][2]
        sign = 1 if direction == "up" else -1
        total = pd.concat([vecs[k] for k in members]).groupby(level=0).sum()
        drivers = total[total * sign > 0]
        drivers = drivers[drivers.abs() >= 0.2 * drivers.abs().max()] if len(drivers) else drivers
        best, best_f1 = None, -1.0
        for g_id in sorted({k[0] for k in members}):
            g = set(m.group_by_id[g_id].skus)
            inter = g & set(drivers.index)
            precision = len(inter) / len(g) if g else 0
            recall = float(drivers[list(inter)].abs().sum() / drivers.abs().sum()) if len(drivers) else 0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
            if f1 > best_f1:
                best, best_f1 = g_id, f1
        rows = sig.set_index(["group", "district", "direction"]).loc[[k for k in members if k[0] == best]]
        districts = sorted({k[1] for k in members if k[0] == best}) or sorted({k[1] for k in members})
        findings.append({
            "group": best,
            "direction": direction,
            "districts": districts,
            "related": sorted({k[0] for k in members} - {best}),
            "statistic": float(rows.statistic.max()),
            "p_value": float(rows.p_value.min()),
            "q_value": float(rows.q_value.min()),
            "alarm_date": pd.to_datetime(rows.first_cross).min(),
            "run_start": pd.to_datetime(rows.run_start).min(),
            "attribution_f1": round(best_f1, 2),
        })
    # the same best tag can win in several district clusters: merge them into one finding
    merged: dict[tuple, dict] = {}
    for f in findings:
        key = (f["group"], f["direction"])
        if key not in merged:
            merged[key] = f
            continue
        m_ = merged[key]
        m_["districts"] = sorted(set(m_["districts"]) | set(f["districts"]))
        m_["related"] = sorted(set(m_["related"]) | set(f["related"]))
        m_["statistic"] = max(m_["statistic"], f["statistic"])
        m_["p_value"] = min(m_["p_value"], f["p_value"])
        m_["q_value"] = min(m_["q_value"], f["q_value"])
        m_["alarm_date"] = min(m_["alarm_date"], f["alarm_date"])
        m_["run_start"] = min(m_["run_start"], f["run_start"])
    findings = sorted(merged.values(), key=lambda f: -f["statistic"])
    return findings[:MAX_FINDINGS]


def _share_stats(group_id: str, districts: list[str], start: pd.Timestamp, as_of: pd.Timestamp) -> dict:
    m = monitoring()
    s = m.series[(m.series.group == group_id) & m.series.district.isin(districts)]
    lower = max(pd.Timestamp(month_start(as_of)), pd.Timestamp(start), as_of-pd.Timedelta(days=13))
    now = s[(s.date >= lower) & (s.date <= as_of)]
    return {"share_now": float(now.actual_share.mean()), "share_expected": float(now.expected_share.mean())}


def _shift_share(group_id: str, districts: list[str], start: pd.Timestamp, as_of: pd.Timestamp) -> dict:
    """Weekly units: the 4 weeks before the change started vs the last 2 weeks."""
    m = monitoring()
    g = set(m.group_by_id[group_id].skus)
    a = m.actual.assign(district=m.actual.store_id.map(m.store_district))
    a = a[a.district.isin(districts)]
    base = a[(a.date >= start - pd.Timedelta(days=28)) & (a.date < start)]
    now = a[(a.date > as_of - pd.Timedelta(days=14)) & (a.date <= as_of)]
    if base.empty:
        hist = read_sql("SELECT o.date, o.sku, o.ordered_units, s.district FROM store_orders o JOIN stores s ON s.id=o.store_id WHERE o.date BETWEEN :a AND :b",
                        a=(start - pd.Timedelta(days=28)).date(), b=(start - pd.Timedelta(days=1)).date())
        base = hist[hist.district.isin(districts)]
    tb, gb = base.ordered_units.sum() / 4, base[base.sku.isin(g)].ordered_units.sum() / 4
    tn, gn = now.ordered_units.sum() / 2, now[now.sku.isin(g)].ordered_units.sum() / 2
    d = decompose(tb, gb, tn, gn)
    return {"volume": d.volume, "mix": d.mix, "interaction": d.interaction, "share_before": d.share_before, "share_after": d.share_now}


def detect(as_of: date) -> list[dict]:
    """Findings for a plan date: CUSUM alarms -> clusters -> investigator -> shift-share -> text."""
    m = monitoring()
    art = artifacts()
    ts = pd.Timestamp(as_of) - pd.Timedelta(days=1)  # data through yesterday
    cal = m.calibration_for(as_of)
    current_series = m.series_for(as_of, through=ts)
    alarms = cusum.alarms_as_of(current_series, cal, ts)
    training_tmax = float(art.static.weather[art.static.weather.date <= pd.Timestamp(art.run_for(as_of).model.trained_through)].tmax.max())
    promotions = read_sql("SELECT sku, start_date, end_date, discount_pct, note FROM promotions")
    product_info = read_sql("SELECT sku, launch_date FROM products").merge(art.static.products[["sku","family"]],on="sku")
    out = []
    for f in _cluster(alarms, ts):
        g = m.group_by_id[f["group"]]
        v = investigate(
            skus=list(g.skus), districts=f["districts"], direction=f["direction"], start=f["run_start"], as_of=ts,
            actual=m.actual, expected=m.expectations, store_district=m.store_district, promotions=promotions,
            weather=art.static.weather, training_tmax=training_tmax, product_info=product_info,
        )
        f.update(_share_stats(f["group"], f["districts"], f["run_start"], ts))
        ss = _shift_share(f["group"], f["districts"], f["run_start"], ts)
        f.update({"effect_volume": ss["volume"], "effect_mix": ss["mix"], "effect_interaction": ss["interaction"],
                  "share_before": ss["share_before"]})
        f.update({"kind": "significant", "source": "scan", "classification": v.label, "confidence": v.confidence,
                  "checks": [c.__dict__ for c in v.checks], "hypotheses": v.hypotheses,
                  "display": narrator.group_display(g.id, g.name), "threshold": cal.h})
        f["explanation"] = narrator.explain_finding(f)
        out.append(f)
    # explained side effects (mirror shares) go last; the planner reads real changes first
    out.sort(key=lambda f: (f["classification"] == "mirror", -f["statistic"]))
    flagged = {(f["group"], f["direction"]) for f in out} | {(r, f["direction"]) for f in out for r in f["related"]}
    reviews = review_near_misses(alarms, current_series, cal, ts)
    m.review_log[as_of.isoformat()] = reviews
    for w in sorted(reviews,key=lambda row:-row["pooled_statistic"]):
        if not w["confirmed"] or (w["group"], w["direction"]) in flagged:
            continue
        g = m.group_by_id[w["group"]]
        flagged.add((w["group"],w["direction"]))
        districts = w.get("districts") or sorted(m.store_district.unique())
        stats = _share_stats(w["group"], districts, ts - pd.Timedelta(days=42), ts)
        out.append({
            "group": w["group"], "direction": w["direction"], "districts": districts, "related": [],
            "statistic": w["pooled_statistic"], "p_value": cal.p_value(w["pooled_statistic"]), "q_value": 1.0,
            "alarm_date": None, "run_start": max(pd.Timestamp(month_start(as_of)), ts - pd.Timedelta(days=42)), "attribution_f1": None,
            "effect_volume": 0.0, "effect_mix": 0.0, "effect_interaction": 0.0, "share_before": stats["share_expected"],
            "kind": "weak", "source": "ai_review", "review_reason": w["reason"], "classification": "unsure", "confidence": 0.4,
            "checks": [{"name":w["method"],"passed":w["confirmed"],"detail":w["reason"],"data":w}], "hypotheses": [], "display": narrator.group_display(g.id, g.name), "threshold": cal.h,
            **stats,
            "explanation": f"{narrator.group_display(g.id,g.name)}: {w['reason'].lower()}. "
                           f"The exploratory check reaches {w['pooled_statistic']:.1f} against {w['threshold']:.1f}. "
                           "Watch this possibility; it has not passed the main significance gate.",
        })
    for finding in out:
        finding["model_version"] = art.run_for(as_of).model.version
        finding["evidence_through"] = ts.date().isoformat()
    return out


# --------------------------------------------------------------------------- adjustments


def default_directions(findings: list[dict]) -> list[dict]:
    """The AI draft of the direction board."""
    items = []
    for f in findings:
        if f["kind"] != "significant":
            continue
        lift = f["share_now"] / max(f["share_expected"], 1e-6)
        if f["classification"] == "persistent":
            bucket = "more" if f["direction"] == "up" else "less"
            factor = float(np.clip(lift, *FACTOR_BOUNDS))
        else:
            bucket, factor = "hold", 1.0
        items.append({"bucket": bucket, "tag_id": f["group"], "districts": f["districts"], "factor": round(factor, 3),
                      "finding_group": f["group"], "note": f["display"],
                      "origin_model_version": f.get("model_version"), "evidence_through": f.get("evidence_through")})
    return items


def sku_adjustments(directions: list[dict], store_split: pd.DataFrame) -> pd.Series:
    """Per SKU multiplier: 1 + (factor - 1) x share of the SKU's demand in the affected districts."""
    m = monitoring()
    split = store_split.assign(district=store_split.store_id.map(m.store_district))
    share = split.pivot_table(index="sku", columns="district", values="mean", aggfunc="sum").fillna(0.0)
    share = share.div(share.sum(axis=1), axis=0)
    adj = pd.Series(1.0, index=share.index)
    for d in directions:
        if d["bucket"] not in ("more", "less", "clear") or not (d.get("tag_id") or d.get("sku")):
            continue
        g = m.group_by_id.get(d.get("tag_id"))
        skus = [s for s in ([d["sku"]] if d.get("sku") else (g.skus if g else [])) if s in adj.index]
        w = share.loc[skus, [c for c in d["districts"] if c in share.columns]].sum(axis=1)
        if d["bucket"] == "clear":
            adj.loc[skus] *= 1 - w
            continue
        adj.loc[skus] *= 1 + (d["factor"] - 1) * w
    return adj.clip(0.0, 2.0)


# --------------------------------------------------------------------------- purchase suggestions


def inventory_position(as_of: date) -> pd.DataFrame:
    """On hand at the end of the previous day plus purchase orders not yet received."""
    prev = as_of - timedelta(days=1)
    inv = read_sql("SELECT sku, on_hand_units FROM node_inventory WHERE date = :d", d=prev)
    po = read_sql(
        """SELECT po.sku, SUM(po.cases * p.units_per_case) AS on_order FROM purchase_orders po JOIN products p USING (sku)
           WHERE po.source = 'history' AND po.order_date < :d AND (po.received_date IS NULL OR po.received_date >= :d) GROUP BY po.sku""",
        d=as_of,
    )
    out = inv.merge(po, on="sku", how="left").fillna({"on_order": 0})
    out["on_order"] = out.on_order.astype(int)
    return out


def active_directions(as_of: date, directions: list[dict], model) -> list[dict]:
    """Retire older approved multipliers only when their observed evidence was trained in.

    Unknown provenance is retained for backwards compatibility; callers carrying an
    old direction must supply evidence_through plus origin_model_version. Historical
    plan rows are never mutated by this lifecycle transition.
    """
    active = []
    for direction in directions:
        origin = direction.get("origin_model_version")
        through = direction.get("evidence_through")
        if through and pd.Timestamp(through).date() >= as_of:
            continue  # a historical decision cannot use later evidence
        if origin and through and origin != model.version and pd.Timestamp(through).date() <= model.trained_through:
            continue
        active.append(dict(direction))
    return active


def suggest_orders(as_of: date, directions: list[dict], service_level: float | None = None,
                   position: pd.DataFrame | None = None, goal: str = "margin", only_due: bool = False,
                   pending_arrivals: dict | None = None, weather_scenario=None) -> pd.DataFrame:
    art = artifacts()
    st = art.static
    monthly = art.run_for(as_of)
    model = monthly.model
    directions = active_directions(as_of, directions, model)
    fc, split = protection_forecast(model, st, as_of - timedelta(days=1), order_calendar=True, weather_scenario=weather_scenario)
    if service_level is None:
        service_level = {"fill_rate": 0.97, "sales": 0.98}.get(goal)
    adj = sku_adjustments(directions, split)
    pos = position if position is not None else inventory_position(as_of)
    prod = st.products.set_index("sku")
    items = []
    for r in fc.itertuples():
        p = prod.loc[r.sku]
        pr = pos[pos.sku == r.sku]
        a = float(adj.get(r.sku, 1.0))
        items.append(SkuInput(
            sku=r.sku, mean=float(r.mean) * a if not only_due or int(p.order_weekday) == as_of.weekday() else 0.0, pdays=int(r.pdays), price=float(p.price_hkd), cost=float(p.cost_hkd),
            units_per_case=int(p.units_per_case), cases_per_pallet=int(p.cases_per_pallet), moq_cases=int(p.moq_cases),
            on_hand=int(pr.on_hand_units.iloc[0]) if len(pr) else 0, on_order=int(pr.on_order.iloc[0]) if len(pr) else 0,
            lead_days=int(p.lead_time_days), adjustment=a,
        ))
    capacity = float(read_sql("SELECT capacity_pallets FROM nodes WHERE id = 'DC1'").capacity_pallets.iloc[0])
    baseline, arrival_mask = capacity_projection(as_of, pos, st, model, adj, pending_arrivals, weather_scenario=weather_scenario)
    plan = plan_orders(items, monthly.ratio_values, capacity, service_level,
                       capacity_baseline=baseline, arrival_mask=arrival_mask)
    wd = prod.order_weekday.reindex(plan.sku).to_numpy()
    plan["model_version"] = model.version
    plan["trained_through"] = model.trained_through
    plan["order_date"] = [as_of + timedelta(days=int((w - as_of.weekday()) % 7)) for w in wd]
    return plan


_CAPACITY_DEMAND_CACHE = {}


def capacity_projection(as_of, position, static, model, adjustment, pending_arrivals=None, weather_scenario=None):
    """Forecast occupancy immediately after each arrival, before that day's shipments.

    Baseline is unclipped cumulative inventory; new-order arrivals add to this ledger.
    Subtract only issued forecasts, never future observed demand. Realized capacity is uncertain.
    """
    prod = static.products.set_index("sku")
    skus = list(prod.index)
    wait = (prod.order_weekday - as_of.weekday()) % 7
    new_arrival = wait + prod.lead_time_days
    horizon = int(new_arrival.max()) + 1
    if pending_arrivals is None:
        rows = read_sql("""SELECT po.sku, po.cases*p.units_per_case AS units,
                           po.expected_date AS arrival_date
                           FROM purchase_orders po JOIN products p USING(sku)
                           WHERE po.source = 'history' AND po.order_date < :d AND (po.received_date IS NULL OR po.received_date >= :d)""", d=as_of)
        pending_arrivals = {}
        for r in rows.itertuples():
            d = max(as_of, r.arrival_date)
            pending_arrivals.setdefault(d, pd.Series(0.,index=skus))[r.sku] += r.units
    if pending_arrivals:
        horizon = max(horizon, max(((d-as_of).days+1 for d in pending_arrivals if d >= as_of), default=0))
    pos = position.set_index("sku").reindex(skus).fillna(0)
    dates = pd.date_range(as_of, periods=horizon)
    key = (id(model), as_of, horizon, weather_scenario)
    if key not in _CAPACITY_DEMAND_CACHE:
        demand = daily_mean(model, static, as_of-timedelta(days=1), dates, weather_scenario=weather_scenario).groupby(["date","sku"])["mean"].sum().unstack("sku").reindex(columns=skus)
        _CAPACITY_DEMAND_CACHE[key] = demand
    demand = _CAPACITY_DEMAND_CACHE[key].to_numpy()*adjustment.reindex(skus).fillna(1).to_numpy()[None,:]
    stock = pos.on_hand_units.to_numpy(dtype=float).copy()
    baseline = []
    for day, d in enumerate(dates):
        if d.date() in pending_arrivals:
            stock += pending_arrivals[d.date()].reindex(skus).fillna(0).to_numpy()
        baseline.append(stock.copy())
        stock -= demand[day]
        # Unfilled demand cannot consume future arrivals. Clip after shipping.
        stock = np.maximum(stock,0)
    baseline = np.array(baseline)
    mask = np.arange(horizon)[:,None] >= new_arrival.to_numpy()[None,:]
    return baseline, mask


def confirmation_capacity(as_of: date, cases: dict[str, int]) -> dict:
    """Check a proposed case map on the same dated occupancy path as suggestions."""
    art = artifacts()
    skus = list(art.static.products.sku)
    with session_scope() as session:
        directions = [{"bucket":r.bucket,"tag_id":r.tag_id,"sku":r.sku,"districts":r.districts,"factor":r.factor}
                      for r in session.scalars(select(DirectionItem).where(DirectionItem.plan_id==plan_id(as_of))).all()]
    model = art.run_for(as_of).model
    directions = active_directions(as_of, directions, model)
    _, split = protection_forecast(model, art.static, as_of-timedelta(days=1), order_calendar=True)
    adjustment = sku_adjustments(directions, split)
    baseline, mask = capacity_projection(as_of, inventory_position(as_of), art.static,
        model, adjustment)
    prod = art.static.products.set_index("sku")
    upc = prod.units_per_case.to_numpy()
    upp = (prod.units_per_case*prod.cases_per_pallet).to_numpy()
    added = np.array([max(0,int(cases.get(s,0))) for s in skus])*upc
    inherited = (np.maximum(baseline,0)/upp[None,:]).sum(axis=1)
    projected = (np.maximum(baseline+mask*added[None,:],0)/upp[None,:]).sum(axis=1)
    capacity = float(read_sql("SELECT capacity_pallets FROM nodes WHERE id='DC1'").capacity_pallets.iloc[0])
    violation = float(np.maximum(projected-np.maximum(capacity,inherited),0).max())
    return {"capacity_pallets":capacity, "projected_peak_pallets":float(projected.max()),
            "inherited_peak_pallets":float(inherited.max()),
            "incremental_overcapacity_pallets":violation, "feasible":violation<=1e-8,
            "model_run": art.run_for(as_of).metadata,
            "series":[{"date":(as_of+timedelta(days=i)).isoformat(),"value":float(v)} for i,v in enumerate(projected)]}


def reason_text(r, names: dict[str, str], directions: list[dict]) -> str:
    parts = [f"{r.pdays}-day protection period: p50 demand {r.demand_p50:,.0f} units"]
    if abs(r.adjustment - 1) > 0.005:
        parts.append(f"adjusted {r.adjustment - 1:+.0%} for this week's direction")
    parts.append(f"target {r.target_units:,.0f} at the {r.critical_ratio:.0%} service point")
    parts.append(f"position {r.inventory_position:,.0f} (on hand {r.on_hand_units:,} + on order {r.on_order_units:,})")
    if r.capacity_cut_cases:
        parts.append(f"{r.capacity_cut_cases} cases held back by cold-store capacity")
    return "; ".join(parts) + "."


# --------------------------------------------------------------------------- watch items


def watch_items(findings: list[dict], directions: list[dict]) -> list[dict]:
    items = [
        {"kind": "fill_rate", "title": "Fill rate to stores", "assumption": "The plan keeps store orders filled at 97% or better", "scope": {}, "origin": "baseline"},
        {"kind": "days_cover", "title": "Stockout risk: cover below lead time", "assumption": "SKU stock cover, using trailing seven-day demand, should exceed supplier lead time", "scope": {"mode":"below_lead"}, "origin": "baseline"},
        {"kind": "days_cover", "title": "Excess stock cover", "assumption": "Flag SKUs with cover above twice lead time plus the weekly review interval, including stock with no recent demand", "scope": {"mode":"excess"}, "origin": "baseline"},
        {"kind": "capacity", "title": "Plan arrival projection", "assumption": "Proposed and confirmed quantities fit on the plan's dated arrival path; this is a forecast, not observed stock", "scope": {"mode":"projected"}, "origin": "baseline"},
        {"kind": "po_delay", "title": "Late purchase orders", "assumption": "Suppliers deliver on the expected date", "scope": {}, "origin": "baseline"},
    ]
    m = monitoring()
    for d in directions:
        g = m.group_by_id.get(d.get("tag_id") or "")
        if not g:
            continue
        name = narrator.group_display(g.id, g.name)
        if d["bucket"] == "more":
            items.append({"kind": "tag_share", "title": f"{name}: is the rise continuing?", "assumption": f"{name} stays above its normal share in {', '.join(d['districts'])}",
                          "scope": {"group": g.id, "districts": d["districts"]}, "origin": "decision"})
        elif d["bucket"] == "less":
            items.append({"kind": "tag_share", "title": f"{name}: is the decline continuing?", "assumption": f"{name} stays below its normal share; cutting orders does not cause stockouts",
                          "scope": {"group": g.id, "districts": d["districts"]}, "origin": "decision"})
        elif d["bucket"] == "hold":
            items.append({"kind": "tag_share", "title": f"{name}: compare with expected share", "assumption": f"Keep baseline orders while reviewing whether {name} moves toward its expected share",
                          "scope": {"group": g.id, "districts": d["districts"]}, "origin": "decision"})
    for f in findings:
        if f["kind"] == "weak":
            items.append({"kind": "tag_share", "title": f"{f['display']}: weak signal", "assumption": f"{f['display']} may be forming a network-wide trend",
                          "scope": {"group": f["group"], "districts": f["districts"]}, "origin": "decision"})
    return items


# --------------------------------------------------------------------------- persistence


def plan_id(week_start: date) -> str:
    return f"P{week_start:%Y%m%d}"


def build_plan(week_start: date, *, stage: str = "discover", accept_defaults: bool = False) -> str:
    """Create (or recreate) the plan for a Monday."""
    pid = plan_id(week_start)
    with session_scope() as existing_session:
        if existing_session.get(Plan, pid) is not None:
            raise ValueError(f"Plan {pid} already exists; update it to preserve user decisions")
    findings = detect(week_start)
    directions = default_directions(findings)
    orders = suggest_orders(week_start, directions)
    names = dict(read_sql("SELECT sku, name FROM products").values)
    now = datetime(week_start.year, week_start.month, week_start.day, 9, 0)
    with session_scope() as s:
        for model in (Question, DirectionItem, PurchaseSuggestion, WatchItem, Decision):
            s.execute(delete(model).where(model.plan_id == pid))
        old = s.scalars(select(Finding.id).where(Finding.plan_id == pid)).all()
        if old:
            s.execute(delete(Hypothesis).where(Hypothesis.finding_id.in_(old)))
            s.execute(delete(Finding).where(Finding.plan_id == pid))
        s.execute(delete(Plan).where(Plan.id == pid))
        s.flush()
        s.add(Plan(id=pid, week_start=week_start, stage=stage, goal="margin", created_at=now,
                   summary={"findings": len(findings), "orders_due": int((orders.final_cases > 0).sum()),
                            "model_run":artifacts().run_for(week_start).metadata,
                            "weak_reviews": monitoring().review_log.get(week_start.isoformat(),[]),
                            "direction_provenance": [{"tag_id":d.get("tag_id"),"origin_model_version":d.get("origin_model_version"),"evidence_through":d.get("evidence_through")} for d in directions]}))
        s.flush()
        for i, f in enumerate(findings):
            fid = f"{pid}-F{i + 1}"
            s.add(Finding(
                id=fid, plan_id=pid, kind=f["kind"], tag_id=f["group"], district=", ".join(f["districts"]), direction=f["direction"],
                alarm_date=f["alarm_date"].date() if f.get("alarm_date") is not None and not pd.isna(f["alarm_date"]) else None,
                statistic=f["statistic"], threshold=f["threshold"], p_value=f["p_value"], q_value=f["q_value"],
                share_before=f.get("share_expected", 0.0), share_now=f.get("share_now", 0.0),
                effect_volume=f["effect_volume"], effect_mix=f["effect_mix"], effect_interaction=f["effect_interaction"],
                source=f["source"], review_reason=f.get("review_reason"), classification=f["classification"], explanation=f["explanation"],
                evidence={"checks": f["checks"], "related": f["related"], "districts": f["districts"], "display": f["display"],
                          "attribution_f1": f["attribution_f1"], "confidence": f["confidence"],
                          "model_version":f.get("model_version"), "evidence_through":f.get("evidence_through")},
            ))
            for j, h in enumerate(f["hypotheses"]):
                s.add(Hypothesis(id=f"{fid}-H{j + 1}", finding_id=fid, cause=h["label"], label=h["label"], text=h["text"],
                                 score=h["score"], evidence={}, selected=(j == 0)))
            if f["kind"] == "significant":
                q = narrator.question_for(f)
                s.add(Question(id=f"{fid}-Q", plan_id=pid, stage="discover", finding_id=fid, text=q["text"],
                               options={"options": q["options"], "recommended": q["recommended"]},
                               answer=q["recommended"] if accept_defaults else None, answered_at=now if accept_defaults else None))
        for k, d in enumerate(directions):
            fid = next((f"{pid}-F{i + 1}" for i, f in enumerate(findings) if f["group"] == d["finding_group"]), None)
            s.add(DirectionItem(id=f"{pid}-D{k + 1}", plan_id=pid, bucket=d["bucket"], tag_id=d["tag_id"], districts=d["districts"],
                                factor=d["factor"], finding_id=fid, note=d["note"]))
        for r in orders.itertuples():
            s.add(PurchaseSuggestion(
                plan_id=pid, sku=r.sku, order_date=r.order_date, protection_days=int(r.pdays), demand_p10=float(r.demand_p10),
                demand_p50=float(r.demand_p50), demand_p90=float(r.demand_p90), adjustment=float(r.adjustment), critical_ratio=float(r.critical_ratio),
                target_units=float(r.target_units), on_hand_units=int(r.on_hand_units), on_order_units=int(r.on_order_units),
                inventory_position=int(r.inventory_position), suggested_cases=int(r.suggested_cases), capacity_cut_cases=int(r.capacity_cut_cases),
                final_cases=int(r.final_cases) if accept_defaults else None, status="confirmed" if accept_defaults else "suggested",
                reason=reason_text(r, names, directions),
            ))
        for w in watch_items(findings, directions):
            s.add(WatchItem(id=f"{pid}-W{hashlib.sha256(w['title'].encode()).hexdigest()[:12]}", plan_id=pid, kind=w["kind"], title=w["title"],
                            assumption=w["assumption"], scope=w["scope"], origin=w["origin"], status="active"))
        if accept_defaults:
            s.add(Decision(plan_id=pid, stage="direction", key="accepted_ai_draft", value={"directions": len(directions)}, source="system", created_at=now))
    return pid


def recompute_orders(pid: str) -> None:
    """Re-run the replenishment step after the planner changed the direction board or goal."""
    with session_scope() as s:
        plan = s.get(Plan, pid)
        dirs = [{"bucket": d.bucket, "tag_id": d.tag_id, "sku": d.sku, "districts": d.districts, "factor": d.factor}
                for d in s.scalars(select(DirectionItem).where(DirectionItem.plan_id == pid)).all()]
        week, sl, goal = plan.week_start, plan.service_level, plan.goal
    orders = suggest_orders(week, dirs, service_level=sl, goal=goal)
    names = dict(read_sql("SELECT sku, name FROM products").values)
    with session_scope() as s:
        s.execute(delete(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == pid))
        for r in orders.itertuples():
            s.add(PurchaseSuggestion(
                plan_id=pid, sku=r.sku, order_date=r.order_date, protection_days=int(r.pdays), demand_p10=float(r.demand_p10),
                demand_p50=float(r.demand_p50), demand_p90=float(r.demand_p90), adjustment=float(r.adjustment), critical_ratio=float(r.critical_ratio),
                target_units=float(r.target_units), on_hand_units=int(r.on_hand_units), on_order_units=int(r.on_order_units),
                inventory_position=int(r.inventory_position), suggested_cases=int(r.suggested_cases), capacity_cut_cases=int(r.capacity_cut_cases),
                final_cases=None, status="suggested", reason=reason_text(r, names, dirs),
            ))
