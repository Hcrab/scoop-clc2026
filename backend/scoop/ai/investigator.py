"""C4 - the investigator: explains alarms with a fixed checklist of data checks.

The investigator never decides significance; CUSUM and Benjamini-Hochberg do. For each
finding it runs deterministic checks (each one is a query a tool-using model would call),
scores the possible causes, and recommends a label the planner can accept or change:

    data_issue   the excess sits in one store on one or two days
    one_off      the excess overlaps a promotion of the group's products
    weather      the excess sits on days hotter than anything in the training history
    mirror       the share moved but the group's own units did not: another group moved
    persistent   the change is spread across stores and still present in the last week
    unsure       none of the above is clear

It also re-tests near-miss charts within a weekly budget (weak-signal review).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..algorithms import cusum

REVIEW_BUDGET = 10


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    data: dict = field(default_factory=dict)


@dataclass
class Verdict:
    label: str
    confidence: float
    checks: list[Check]
    hypotheses: list[dict]


def _window(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return frame[(frame.date >= start) & (frame.date <= end)]


def investigate(
    *,
    skus: list[str],
    districts: list[str],
    direction: str,
    start: pd.Timestamp,
    as_of: pd.Timestamp,
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    store_district: pd.Series,
    promotions: pd.DataFrame,
    weather: pd.DataFrame,
    training_tmax: float,
) -> Verdict:
    sign = 1 if direction == "up" else -1
    stores = list(store_district[store_district.isin(districts)].index)
    a = _window(actual, start, as_of)
    e = _window(expected, start, as_of)
    a = a[a.store_id.isin(stores) & a.sku.isin(skus)]
    e = e[e.store_id.isin(stores) & e.sku.isin(skus)]
    j = a.merge(e[["date", "store_id", "sku", "mean"]], on=["date", "store_id", "sku"], how="left").fillna({"mean": 0.0})
    j["excess"] = j.ordered_units - j["mean"]
    total_excess = float(j.excess.sum())
    checks: list[Check] = []

    # 1. concentration in one store and few days (bulk or data error)
    by_store_day = j.groupby(["store_id", "date"]).excess.sum() * sign
    pos = by_store_day[by_store_day > 0]
    top2 = float(pos.nlargest(2).sum() / pos.sum()) if pos.sum() > 0 else 0.0
    top_cell = pos.idxmax() if len(pos) else None
    # also look at the last 7 days: a fresh bulk order can dominate the latest jump
    recent_cells = pos[pos.index.get_level_values("date") > as_of - pd.Timedelta(days=7)]
    recent_top2 = float(recent_cells.nlargest(2).sum() / recent_cells.sum()) if recent_cells.sum() > 0 else 0.0
    if recent_top2 > top2 and recent_cells.sum() > 0.3 * pos.sum():
        top2, top_cell = recent_top2, recent_cells.idxmax()
    concentrated = top2 >= 0.5 and pos.sum() > 0
    checks.append(Check("concentration", concentrated,
                        f"Top two store-days carry {top2:.0%} of the excess" + (f" ({top_cell[0]} on {top_cell[1].date()})" if top_cell else ""),
                        {"top2_share": round(top2, 3), "store": top_cell[0] if top_cell else None}))

    # 2. overlap with promotions of the group's products
    pr = promotions[promotions.sku.isin(skus) & (pd.to_datetime(promotions.end_date) >= start) & (pd.to_datetime(promotions.start_date) <= as_of)]
    promo_days = set()
    for r in pr.itertuples():
        promo_days.update(pd.date_range(r.start_date, r.end_date))
    in_promo = j[j.date.isin(promo_days)].excess.sum() * sign
    promo_share = float(in_promo / (total_excess * sign)) if total_excess * sign > 0 else 0.0
    promo_hit = len(pr) > 0 and promo_share >= 0.5
    checks.append(Check("promotion", promo_hit,
                        f"{len(pr)} promotions overlap; {promo_share:.0%} of the excess falls on promotion days" if len(pr) else "No promotion overlaps the window",
                        {"promotions": pr.note.drop_duplicates().tolist()[:3], "share": round(promo_share, 3)}))

    # 3. record heat
    w = _window(weather.assign(date=pd.to_datetime(weather.date)), start, as_of)
    hot_days = set(w[w.tmax > training_tmax].date)
    hot_share = float(j[j.date.isin(hot_days)].excess.sum() * sign / (total_excess * sign)) if hot_days and total_excess * sign > 0 else 0.0
    heat_hit = bool(hot_days) and hot_share >= 0.4
    checks.append(Check("record_heat", heat_hit,
                        f"{len(hot_days)} days above the training maximum of {training_tmax:.1f}C carry {hot_share:.0%} of the excess" if hot_days else "No day above the training temperature range",
                        {"hot_days": len(hot_days), "share": round(hot_share, 3)}))

    # 4. absolute vs relative: did the group's own units move?
    units_lift = float(j.ordered_units.sum() / max(j["mean"].sum(), 1.0))
    mirror = (direction == "up" and units_lift < 1.03) or (direction == "down" and units_lift > 0.97)
    checks.append(Check("own_units", not mirror, f"Group units are {units_lift - 1:+.0%} against the model", {"units_lift": round(units_lift, 3)}))

    # 5. spread across stores
    by_store = j.groupby("store_id").excess.sum() * sign
    spread = int((by_store > 0).sum())
    n_stores = len(stores)
    checks.append(Check("spread", spread >= max(2, int(0.6 * n_stores)), f"{spread} of {n_stores} stores show the change", {"stores": spread, "of": n_stores}))

    # 6. persistence: still there in the last 7 days
    recent = j[j.date > as_of - pd.Timedelta(days=7)]
    recent_lift = float(recent.ordered_units.sum() / max(recent["mean"].sum(), 1.0))
    persists = (recent_lift > 1.03) if direction == "up" else (recent_lift < 0.97)
    days = int((as_of - start).days) + 1
    checks.append(Check("persistence", persists and days >= 7, f"Last 7 days: units {recent_lift - 1:+.0%}; running for {days} days", {"recent_lift": round(recent_lift, 3), "days": days}))

    fading = not persists and days >= 7
    scores = {
        "data_issue": 0.9 if concentrated else 0.05,
        "one_off": 0.85 if promo_hit else (0.6 if fading else 0.05),
        "weather": 0.7 if heat_hit else 0.05,
        "mirror": 0.6 if mirror else 0.05,
        "persistent": 0.2 + 0.35 * checks[4].passed + 0.35 * checks[5].passed,
    }
    if concentrated or promo_hit:
        scores["persistent"] *= 0.3
    label = max(scores, key=scores.get)
    conf = scores[label]
    if conf < 0.5:
        label, conf = "unsure", 0.4
    text = {
        "data_issue": "A one-off bulk order or data error in a single store",
        "one_off": "A temporary lift (promotion or a burst that has already faded)",
        "weather": "Record heat beyond the model's experience",
        "mirror": "Only the share moved; another group's change is behind it",
        "persistent": "A genuine preference shift that is spreading",
        "unsure": "Not enough evidence yet",
    }
    hyps = [{"label": k, "score": round(v, 2), "text": text[k]} for k, v in sorted(scores.items(), key=lambda x: -x[1])]
    return Verdict(label, round(conf, 2), checks, hyps)


def review_near_misses(alarms: pd.DataFrame, series: pd.DataFrame, cal: cusum.Calibration, as_of: pd.Timestamp, budget: int = REVIEW_BUDGET) -> list[dict]:
    """Re-test near-miss charts by pooling districts: a change spread thin across districts can
    stay under every district's threshold while being clear network-wide."""
    near = alarms[alarms.near_miss].copy()
    near["pooled_key"] = near.group + "|" + near.direction
    candidates = near.groupby("pooled_key").statistic.sum().sort_values(ascending=False).head(budget)
    out = []
    for key in candidates.index:
        group, direction = key.split("|")
        part = series[(series.group == group) & (series.date <= as_of) & (series.date >= as_of - pd.Timedelta(days=42))]
        pooled = part.groupby("date").z.sum() / np.sqrt(part.district.nunique())
        up, down = cusum._run(pooled.to_numpy())
        stat = float((up if direction == "up" else down)[-1])
        out.append({"group": group, "direction": direction, "pooled_statistic": round(stat, 2), "threshold": cal.h,
                    "confirmed": stat >= cal.h, "reason": "Pooled across districts: change spread thin across the network"})
    return out
