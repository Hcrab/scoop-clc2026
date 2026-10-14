"""Play: run the warehouse forward from a plan's Monday and compare it with a mechanical rule.

Both runs start from the same closing stock and the same purchase orders already in transit,
and serve the same store orders day by day. Only the new purchasing differs:

* ``scoop``    week 1 uses this plan's order lines (confirmed cases, otherwise the
               suggestion after capacity cuts). Later weeks, if played, run on autopilot:
               each Monday a fresh cohort fit informs orders and each supplier
               day orders with the same order-up-to logic as the planner.
* ``baseline`` the moving-average rule that produced the synthetic history: order up to
               28-day average demand x (lead time + review days) x 1.25.

Store orders are exogenous in the synthetic world (stores do not see warehouse stock), so
replaying them is a fair counterfactual. New orders arrive after the supplier's mean lead time.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .db import read_sql

BASELINE_BUFFER = 1.25
HOT_DAY_C = 33.0
NEAR_FULL = 0.95
_CACHE: dict[str, dict] = {}


def _week_orders(pid: str) -> pd.DataFrame:
    df = read_sql(
        "SELECT sku, order_date, suggested_cases, capacity_cut_cases, final_cases, status FROM purchase_suggestions WHERE plan_id = :p",
        p=pid,
    )
    df["cases"] = np.where(df.final_cases.notna(), df.final_cases.fillna(0), (df.suggested_cases - df.capacity_cut_cases).clip(lower=0))
    df["cases"] = df.cases.astype(int)
    df["order_date"] = pd.to_datetime(df.order_date).dt.date
    return df


def _top(series: pd.Series, names: dict[str, str], n: int = 3) -> list[dict]:
    s = series[series > 0].sort_values(ascending=False).head(n)
    return [{"sku": k, "name": names.get(k, k), "units": int(round(v))} for k, v in s.items()]


def simulate(pid: str, week_start: date, days: int = 7) -> dict:
    orders_week = _week_orders(pid)
    key = hashlib.sha256(json.dumps([pid, days, orders_week[["sku", "cases"]].values.tolist()], default=str).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]

    prod = read_sql(
        """SELECT p.sku, p.name, p.brand, p.price_hkd, p.cost_hkd, p.units_per_case, p.cases_per_pallet, p.moq_cases,
                  s.lead_time_days, s.order_weekday, s.review_days
           FROM products p JOIN suppliers s ON s.id = p.supplier_id ORDER BY p.sku"""
    ).set_index("sku")
    skus = list(prod.index)
    names = prod.name.to_dict()
    start, end = week_start, week_start + timedelta(days=days - 1)
    raw = read_sql(
        "SELECT date, sku, SUM(ordered_units) AS u FROM store_orders WHERE date BETWEEN :a AND :b GROUP BY date, sku",
        a=start - timedelta(days=28), b=end,
    )
    raw["date"] = pd.to_datetime(raw.date).dt.date
    demand = raw.pivot(index="date", columns="sku", values="u").reindex(columns=skus).fillna(0.0)
    inv0 = read_sql("SELECT sku, on_hand_units FROM node_inventory WHERE date = :d", d=start - timedelta(days=1)).set_index("sku").on_hand_units
    open_po = read_sql(
        """SELECT po.sku, po.cases * p.units_per_case AS units, po.received_date, po.expected_date FROM purchase_orders po JOIN products p USING (sku)
           WHERE po.source = 'history' AND po.order_date < :d AND (po.received_date IS NULL OR po.received_date >= :d)""",
        d=start,
    )
    weather = read_sql("SELECT date, tmax FROM weather_daily WHERE date BETWEEN :a AND :b", a=start, b=end)
    weather["date"] = pd.to_datetime(weather.date).dt.date
    tmax = dict(zip(weather.date, weather.tmax))
    capacity = float(read_sql("SELECT capacity_pallets FROM nodes WHERE id = 'DC1'").capacity_pallets.iloc[0])
    upp = (prod.units_per_case * prod.cases_per_pallet).astype(float)
    margin = (prod.price_hkd - prod.cost_hkd).astype(float)

    def initial():
        arrivals: dict[date, pd.Series] = {}
        for r in open_po.itertuples():
            day = r.received_date if r.received_date is not None and not pd.isna(r.received_date) else r.expected_date
            arrivals.setdefault(day, pd.Series(0.0, index=skus))[r.sku] += r.units
        pipeline = open_po.groupby("sku").units.sum().reindex(skus).fillna(0.0).astype(float)
        return inv0.reindex(skus).fillna(0.0).astype(float), arrivals, pipeline

    week_cases = orders_week.set_index("sku").cases.reindex(skus).fillna(0).astype(int)
    week_dates = orders_week.set_index("sku").order_date.reindex(skus)

    runs = {}
    autopilot_notes: list[dict] = []
    for policy in ("scoop", "baseline"):
        on_hand, arrivals, pipeline = initial()
        own_arrivals: dict[date, pd.Series] = {}
        cohort_result = None
        cohort_week = None
        daily, per_sku = [], {"on_hand": [], "shipped": [], "lost": [], "arrived": []}
        d = start
        while d <= end:
            arrived = pd.Series(0.0, index=skus)
            if d in arrivals:
                arrived = arrivals.pop(d)
                on_hand += arrived
                pipeline -= arrived
            pre_ship = float((on_hand / upp).sum())
            dem = demand.loc[d] if d in demand.index else pd.Series(0.0, index=skus)
            ship = np.minimum(on_hand, dem)
            lost = dem - ship
            on_hand = on_hand - ship

            due = [s for s in skus if int(prod.loc[s, "order_weekday"]) == d.weekday()]
            placed = pd.Series(0, index=skus, dtype=int)
            if policy == "scoop" and d < start + timedelta(days=7):
                for s in skus:
                    if week_cases[s] > 0 and week_dates[s] == d:
                        placed[s] = int(week_cases[s])
            elif policy == "scoop" and due:
                from types import SimpleNamespace
                from .algorithms import cohort_model
                from .planning import detect, suggest_orders

                current_week = d - timedelta(days=d.weekday())
                if cohort_week != current_week:
                    cohort_result = cohort_model.fit(SimpleNamespace(week_start=current_week))
                    cohort_week = current_week
                    try:
                        found = detect(d)
                        autopilot_notes.append({"date": d.isoformat(), "findings": [f.get("display", f.get("group", "signal"))
                                                for f in found if f.get("kind") == "significant"][:4]})
                    except Exception:  # CUSUM notes do not control automatic orders
                        pass
                pos = pd.DataFrame({"sku": skus, "on_hand_units": on_hand.round().astype(int).to_numpy(), "on_order": pipeline.round().astype(int).to_numpy()})
                plan = suggest_orders(d, [], position=pos, only_due=True, pending_arrivals=arrivals,
                                      cohort_result=cohort_result).set_index("sku")
                for s in due:
                    placed[s] = int(plan.loc[s, "final_cases"]) if s in plan.index else 0
            elif policy == "baseline":
                for s in due:
                    lead = int(prod.loc[s, "lead_time_days"])
                    hist = demand.loc[d - timedelta(days=28): d - timedelta(days=1), s].mean()
                    need = max(0.0, hist * (lead + int(prod.loc[s, "review_days"])) * BASELINE_BUFFER - (on_hand[s] + ship[s]) - pipeline[s])
                    cases = int(np.ceil(need / prod.loc[s, "units_per_case"]))
                    placed[s] = max(cases, int(prod.loc[s, "moq_cases"])) if cases > 0 else 0
            for s in skus:
                if placed[s] > 0:
                    units = placed[s] * float(prod.loc[s, "units_per_case"])
                    arrive = d + timedelta(days=int(prod.loc[s, "lead_time_days"]))
                    arrivals.setdefault(arrive, pd.Series(0.0, index=skus))[s] += units
                    own_arrivals.setdefault(arrive, pd.Series(0.0, index=skus))[s] += units
                    pipeline[s] += units

            closing = float((on_hand / upp).sum())
            daily.append({
                "date": d.isoformat(), "demand": float(dem.sum()), "shipped": float(ship.sum()), "lost": float(lost.sum()),
                "lost_margin": float((lost * margin).sum()), "on_hand": float(on_hand.sum()), "pallets_pre_ship": pre_ship,
                "pallets": closing, "arrived_units": float(arrived.sum()), "ordered_cases": int(placed.sum()),
                "skus_short": int((lost > 0).sum()),
            })
            per_sku["on_hand"].append(on_hand.round(1).tolist())
            per_sku["shipped"].append(ship.round(1).tolist())
            per_sku["lost"].append(lost.round(1).tolist())
            per_sku["arrived"].append(arrived.round(1).tolist())
            d += timedelta(days=1)
        runs[policy] = {"daily": daily, "per_sku": per_sku, "orders_after": {k.isoformat(): v[v > 0].round().to_dict() for k, v in own_arrivals.items() if k > end}}

    # events, written from the data of both runs
    events = []
    dates = [x["date"] for x in runs["scoop"]["daily"]]
    lost_s = np.array(runs["scoop"]["per_sku"]["lost"])
    lost_b = np.array(runs["baseline"]["per_sku"]["lost"])
    arrived_s = np.array(runs["scoop"]["per_sku"]["arrived"])
    for i, day in enumerate(dates):
        dt = date.fromisoformat(day)
        t = tmax.get(dt)
        if t is not None and t >= HOT_DAY_C:
            dem_today = runs["scoop"]["daily"][i]["demand"]
            avg = float(demand.loc[start - timedelta(days=28): start - timedelta(days=1)].sum(axis=1).mean())
            events.append({"date": day, "kind": "weather", "tone": "neutral",
                           "text": f"{t:.1f}°C. Stores ordered {dem_today:,.0f} units, {dem_today / avg - 1:+.0%} on the four weeks before."})
        week_arrivals = [s for s in skus if arrived_s[i, skus.index(s)] > 0 and week_cases[s] > 0 and week_dates[s] is not None
                         and not pd.isna(week_dates[s]) and week_dates[s] + timedelta(days=int(prod.loc[s, "lead_time_days"])) == dt]
        if week_arrivals:
            cases = int(sum(week_cases[s] for s in week_arrivals))
            events.append({"date": day, "kind": "arrival", "tone": "good",
                           "text": f"This week's orders arrived: {cases:,} cases across {len(week_arrivals)} products.",
                           "skus": [names[s] for s in week_arrivals[:4]]})
        prev_s = lost_s[i - 1] if i else np.zeros(len(skus))
        prev_b = lost_b[i - 1] if i else np.zeros(len(skus))
        new_s = pd.Series(np.where((lost_s[i] > 0) & (prev_s == 0), lost_s[i], 0), index=skus)
        new_b = pd.Series(np.where((lost_b[i] > 0) & (prev_b == 0), lost_b[i], 0), index=skus)
        if new_s.sum() > 0:
            top = _top(new_s, names)
            events.append({"date": day, "kind": "stockout", "tone": "bad", "policy": "scoop",
                           "text": f"Ran out: {', '.join(x['name'] for x in top)} ({int(new_s.sum()):,} units short).", "skus": top})
        saved = pd.Series(np.where((lost_b[i] > 0) & (lost_s[i] == 0), lost_b[i], 0), index=skus)
        if saved.sum() > 0:
            top = _top(saved, names)
            events.append({"date": day, "kind": "kept", "tone": "good",
                           "text": f"Still in stock with Scoop, out with the moving-average rule: {', '.join(x['name'] for x in top)} ({int(saved.sum()):,} units kept).",
                           "skus": top})
        if runs["scoop"]["daily"][i]["pallets_pre_ship"] > NEAR_FULL * capacity:
            events.append({"date": day, "kind": "capacity", "tone": "warn",
                           "text": f"Cold store at {runs['scoop']['daily'][i]['pallets_pre_ship']:.0f} of {capacity:.0f} pallets after deliveries."})
    for note in autopilot_notes:
        if note["findings"]:
            events.append({"date": note["date"], "kind": "scan", "tone": "neutral",
                           "text": "Weekly early warnings: " + "; ".join(note["findings"]) + "."})
    events.sort(key=lambda e: (e["date"], ["weather", "scan", "arrival", "kept", "stockout", "capacity"].index(e["kind"])))

    def summary(policy: str) -> dict:
        rows = runs[policy]["daily"]
        dem = sum(r["demand"] for r in rows)
        return {
            "fill_rate": sum(r["shipped"] for r in rows) / dem if dem else 1.0,
            "lost_units": sum(r["lost"] for r in rows),
            "lost_margin": sum(r["lost_margin"] for r in rows),
            "avg_pallets": float(np.mean([r["pallets"] for r in rows])),
            "peak_pallets": float(max(r["pallets_pre_ship"] for r in rows)),
            "days_over_capacity": int(sum(r["pallets_pre_ship"] > capacity for r in rows)),
            "stockout_sku_days": int((np.array(runs[policy]["per_sku"]["lost"]) > 0).sum()),
            "ending_on_hand": rows[-1]["on_hand"],
            "ordered_cases": int(sum(r["ordered_cases"] for r in rows)),
        }

    result = {
        "plan_id": pid, "start": start.isoformat(), "end": end.isoformat(), "days": days, "capacity_pallets": capacity,
        "skus": skus, "dates": dates,
        "products": [{"sku": s, "name": names[s], "brand": prod.loc[s, "brand"]} for s in skus],
        "demand": demand.loc[start:end].round(1).values.tolist(),
        "runs": runs, "events": events,
        "summary": {"scoop": summary("scoop"), "baseline": summary("baseline")},
        "notes": {
            "baseline": "Moving-average rule: order up to 28-day average demand x (lead time + review days) x 1.25.",
            "lead_time": "New orders arrive after the supplier's mean lead time; orders placed late in the week may land after the played period.",
            "autopilot": "After the first week, Scoop refits cohort effects and places future orders automatically." if days > 7 else None,
        },
    }
    _CACHE[key] = result
    return result
