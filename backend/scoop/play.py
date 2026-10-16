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
from .api.service import MAX_DAY
from . import intraday
from .config import ORDER_CUTOFF_MINUTE

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


def _admit_receipts(on_hand: pd.Series, due: pd.Series, upp: pd.Series,
                    capacity: float) -> pd.Series:
    """Admit whole units proportionally, retaining the rest outside cold storage.

    The daily model admits units, even though purchase orders are placed in cases.
    Ties in largest-remainder rounding follow SKU order for reproducibility.
    """
    free = capacity - float((on_hand / upp).sum())
    if free < -1e-9:
        raise ValueError("Opening cold-store inventory exceeds physical capacity")
    due = due.astype(float)
    due_pallets = float((due / upp).sum())
    if due_pallets <= max(free, 0.0) + 1e-9:
        return due.copy()
    exact = due * (max(free, 0.0) / due_pallets)
    admitted = np.floor(exact).astype(float)
    room = max(free, 0.0) - float((admitted / upp).sum())
    ranking = sorted(due.index, key=lambda sku: (-(exact[sku] - admitted[sku]), str(sku)))
    # One-unit passes handle different SKU pallet sizes without wasting a slot.
    while True:
        added = False
        for sku in ranking:
            unit_space = 1.0 / upp[sku]
            if admitted[sku] < due[sku] and unit_space <= room + 1e-9:
                admitted[sku] += 1
                room -= unit_space
                added = True
        if not added:
            break
    return admitted


def simulate(pid: str, week_start: date, days: int | None = None) -> dict:
    orders_week = _week_orders(pid)
    prod = read_sql(
        """SELECT p.sku, p.name, p.brand, p.supplier_id, p.price_hkd, p.cost_hkd, p.units_per_case, p.cases_per_pallet, p.moq_cases,
                  s.lead_time_days, s.order_weekday, s.review_days
           FROM products p JOIN suppliers s ON s.id = p.supplier_id ORDER BY p.sku"""
    ).set_index("sku")
    skus = list(prod.index)
    names = prod.name.to_dict()
    suppliers = prod.supplier_id.fillna('DEFAULT').astype(str).tolist() if 'supplier_id' in prod else ['DEFAULT'] * len(skus)
    ordered = orders_week.loc[orders_week.cases > 0, "sku"]
    horizon = max(7, max((int(prod.loc[s, "lead_time_days"]) + 7 for s in ordered if s in prod.index), default=7))
    days = min(days if days is not None else horizon, 21, (MAX_DAY - week_start).days + 1)
    if days < 1:
        raise ValueError("Plan week falls after the demo calendar")
    start, end = week_start, week_start + timedelta(days=days - 1)
    context = read_sql("SELECT summary, goal, service_level FROM plans WHERE id = :p", p=pid)
    settings = read_sql("SELECT value FROM settings WHERE key = 'cohort_overrides'")
    plan_summary = context.summary.iloc[0] if not context.empty else {}
    if isinstance(plan_summary, str):
        plan_summary = json.loads(plan_summary)
    cards = (plan_summary or {}).get("cohort_cards", [])
    goal = context.goal.iloc[0] if not context.empty else "margin"
    service_level = context.service_level.iloc[0] if not context.empty else None
    raw = read_sql(
        "SELECT date, sku, SUM(ordered_units) AS u FROM store_orders WHERE date BETWEEN :a AND :b GROUP BY date, sku",
        a=start - timedelta(days=28), b=end,
    )
    raw["date"] = pd.to_datetime(raw.date).dt.date
    all_dates = [start - timedelta(days=28) + timedelta(days=i) for i in range(days + 28)]
    demand = raw.pivot(index="date", columns="sku", values="u").reindex(index=all_dates, columns=skus).fillna(0.0)
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
    # Use only expectations issued before the plan. Missing day/SKU evidence stays unknown.
    forecast_run = read_sql(
        "SELECT id, trained_through FROM model_runs WHERE trained_through < :d ORDER BY trained_through DESC, created_at DESC LIMIT 1",
        d=start,
    )
    expectations = (read_sql(
        """SELECT date, sku, SUM(p50) AS expected_units FROM daily_expectations
           WHERE run_id = :r AND date BETWEEN :a AND :b GROUP BY date, sku
           HAVING COUNT(DISTINCT store_id) = (SELECT COUNT(*) FROM stores)""",
        r=forecast_run.id.iloc[0], a=start, b=end,
    ) if not forecast_run.empty else pd.DataFrame(columns=["date", "sku", "expected_units"]))
    if not expectations.empty:
        expectations["date"] = pd.to_datetime(expectations.date).dt.date
    upp = (prod.units_per_case * prod.cases_per_pallet).astype(float)
    margin = (prod.price_hkd - prod.cost_hkd).astype(float)
    # All inputs that can change a replay are read before consulting the cache.
    inputs = [pid, start, days,
              orders_week[["sku", "order_date", "cases", "suggested_cases", "capacity_cut_cases", "final_cases"]].to_dict("records"), prod.reset_index().to_dict("records"),
              goal, service_level, plan_summary, settings.to_dict("records"), raw.to_dict("records"),
              inv0.to_dict(), open_po.to_dict("records"), weather.to_dict("records"), capacity,
              forecast_run.to_dict("records"), expectations.to_dict("records")]
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]

    def initial():
        arrivals: dict[date, pd.Series] = {}
        for r in open_po.itertuples():
            day = r.received_date if r.received_date is not None and not pd.isna(r.received_date) else r.expected_date
            arrivals.setdefault(day, pd.Series(0.0, index=skus))[r.sku] += r.units
        pipeline = open_po.groupby("sku").units.sum().reindex(skus).fillna(0.0).astype(float)
        return inv0.reindex(skus).fillna(0.0).astype(float), arrivals, pipeline

    week_cases = orders_week.set_index("sku").cases.reindex(skus).fillna(0).astype(int)
    week_dates = orders_week.set_index("sku").order_date.reindex(skus)
    opening_pallets = float((inv0.reindex(skus).fillna(0.0) / upp).sum())
    if opening_pallets > capacity + 1e-9:
        raise ValueError(f"Opening cold-store inventory {opening_pallets:.3f} pallets exceeds capacity {capacity:.3f}")

    runs = {}
    autopilot_notes: list[dict] = []
    for policy in ("scoop", "baseline"):
        on_hand, arrivals, pipeline = initial()
        own_arrivals: dict[date, pd.Series] = {}
        deferred = pd.Series(0.0, index=skus)
        deferred_own = pd.Series(0.0, index=skus)
        cohort_result = None
        cohort_week = None
        daily, per_sku = [], {"on_hand": [], "shipped": [], "lost": [], "demand": [], "arrived": [], "deferred": [], "placed_cases": [], "pre_ship": []}
        d = start
        while d <= end:
            due_receipts = arrivals.pop(d, pd.Series(0.0, index=skus)) + deferred
            own_due = own_arrivals.pop(d, pd.Series(0.0, index=skus)) + deferred_own
            arrived = _admit_receipts(on_hand, due_receipts, upp, capacity)
            deferred = due_receipts - arrived
            # Attribute same-SKU receipts to inherited transit first for the
            # orders_after diagnostic; this does not change physical admission.
            own_received = pd.Series(0.0, index=skus)
            for s in skus:
                inherited_due = due_receipts[s] - own_due[s]
                own_received[s] = min(own_due[s], max(0.0, arrived[s] - inherited_due))
            deferred_own = own_due - own_received
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
                pending = dict(arrivals)
                if deferred.sum() > 0:
                    next_day = d + timedelta(days=1)
                    pending[next_day] = pending.get(next_day, pd.Series(0.0, index=skus)) + deferred
                plan = suggest_orders(d, [], position=pos, only_due=True, pending_arrivals=pending,
                                      cohort_result=cohort_result, goal=goal,
                                      service_level=service_level)
                # The fitted tree is already retained above. Avoid copying its large
                # metadata into every temporary Series used to read case quantities.
                plan.attrs.clear()
                plan = plan.set_index("sku")
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
                "pallets": closing, "arrived_units": float(arrived.sum()), "deferred_units": float(deferred.sum()),
                "ordered_cases": int(placed.sum()),
                "skus_short": int((lost > 0).sum()),
            })
            per_sku["on_hand"].append(on_hand.round(1).tolist())
            per_sku["shipped"].append(ship.round(1).tolist())
            per_sku["lost"].append(lost.round(1).tolist())
            per_sku["demand"].append(dem.round(1).tolist())
            per_sku["arrived"].append(arrived.round(1).tolist())
            per_sku["deferred"].append(deferred.round(1).tolist())
            per_sku["placed_cases"].append(placed.tolist())
            per_sku["pre_ship"].append((on_hand + ship).round(1).tolist())
            d += timedelta(days=1)
        pending_after = {k.isoformat(): v[v > 0].round().to_dict() for k, v in arrivals.items() if k > end}
        if deferred.sum() > 0:
            pending_after['deferred'] = deferred[deferred > 0].round().to_dict()
        orders_after = {k.isoformat(): v[v > 0].round().to_dict() for k, v in own_arrivals.items() if k > end}
        if deferred_own.sum() > 0:
            orders_after['deferred'] = deferred_own[deferred_own > 0].round().to_dict()
        runs[policy] = {"daily": daily, "per_sku": per_sku, "orders_after": orders_after,
                        "pending_after": pending_after, "pipeline_units_after": pipeline.round(3).to_dict()}

    intraday_data = {'dates': [x['date'] for x in runs['scoop']['daily']], 'skus': skus, 'runs': runs}
    intraday.enrich(intraday_data, suppliers)
    # Presentation events follow Scoop only; comparison data remains in both runs.
    events = []
    dates = [x["date"] for x in runs["scoop"]["daily"]]
    lost_s = np.array(runs["scoop"]["per_sku"]["lost"])
    arrived_s = np.array(runs["scoop"]["per_sku"]["arrived"])
    card_by_sku = {s: [card["id"] for card in cards if s in card.get("skus", []) and card.get("id")]
                   for s in skus}

    def event_links(selected: list[str], through: int, minute: int) -> dict:
        placed = runs["scoop"]["per_sku"]["placed_cases"]
        return {
            "card_ids": sorted({cid for s in selected for cid in card_by_sku[s]}),
            "order_dates": sorted({dates[k] for k in range(through + 1) for s in selected
                                   if placed[k][skus.index(s)] > 0 and (k < through or minute >= ORDER_CUTOFF_MINUTE)}),
        }

    for i, day in enumerate(dates):
        dt = date.fromisoformat(day)
        placed = runs["scoop"]["per_sku"]["placed_cases"][i]
        lines = [
            {"sku": skus[j], "name": names[skus[j]], "cases": int(cases),
             "order_date": day,
             "expected_arrival": (dt + timedelta(days=int(prod.loc[skus[j], "lead_time_days"]))).isoformat(),
             "card_ids": card_by_sku[skus[j]]}
            for j, cases in enumerate(placed) if cases > 0
        ]
        if lines:
            cases = sum(line["cases"] for line in lines)
            events.append({"date": day, "kind": "order", "tone": "neutral", "policy": "scoop",
                           "order_date": day, "cases": cases, "order_count": len(lines), "lines": lines,
                           "automatic": i >= 7,
                           "card_ids": sorted({cid for line in lines for cid in line["card_ids"]}),
                           "text": f"Placed {len(lines):,} orders, {cases:,} cases"})
        t = tmax.get(dt)
        if t is not None and t >= HOT_DAY_C:
            events.append({"date": day, "kind": "weather", "tone": "neutral",
                           "text": f"Day’s high: {t:.1f}°C."})
        if runs["scoop"]["daily"][i]["pallets_pre_ship"] > NEAR_FULL * capacity:
            events.append({"date": day, "kind": "capacity", "tone": "warn",
                           "text": f"Cold store at {runs['scoop']['daily'][i]['pallets_pre_ship']:.0f} of {capacity:.0f} pallets after deliveries."})
    for note in autopilot_notes:
        if note["findings"]:
            events.append({"date": note["date"], "kind": "scan", "tone": "neutral",
                           "text": "Weekly observations: " + "; ".join(note["findings"]) + "."})
    arrival_minutes = intraday_data['intraday']['arrival_minutes']
    for i, day in enumerate(dates):
        dt = date.fromisoformat(day)
        for j, sku in enumerate(skus):
            minute = arrival_minutes[i][j]
            amount = arrived_s[i, j]
            if amount:
                first_week_order = (week_cases[sku] > 0 and not pd.isna(week_dates[sku]) and
                                    week_dates[sku] + timedelta(days=int(prod.loc[sku, 'lead_time_days'])) == dt)
                fully_received = runs['scoop']['per_sku']['deferred'][i][j] == 0
                cases = int(week_cases[sku]) if first_week_order and fully_received else None
                events.append({'date': day, 'kind': 'arrival', 'tone': 'good', 'policy': 'scoop',
                               'sku': sku, 'skus': [sku], 'name': names[sku], 'units': amount,
                               'cases': cases, **event_links([sku], i, minute), 'minute': minute,
                               'text': f"{names[sku]} arrived: {amount:,.0f} units."})

            scoop_loss = lost_s[i, j]
            prior_s = lost_s[i - 1, j] if i else 0
            if scoop_loss > 0 and (prior_s == 0 or arrived_s[i, j] > 0):
                opening = (intraday_data['intraday']['opening_on_hand'][j] if i == 0 else
                           runs['scoop']['per_sku']['on_hand'][i - 1][j])
                minute = intraday.first_shortage_minute(
                    runs['scoop']['per_sku']['demand'][i][j], opening, arrived_s[i, j], arrival_minutes[i][j])
                events.append({'date': day, 'kind': 'stockout', 'tone': 'bad', 'policy': 'scoop',
                               'sku': sku, 'skus': [{'sku': sku, 'name': names[sku], 'units': int(round(scoop_loss))}],
                               'minute': minute, 'text': f"{names[sku]} ran out.",
                               **event_links([sku], i, minute)})
        for event in events:
            if event['date'] != day or 'minute' in event:
                continue
            kind = event['kind']
            if kind == 'order':
                event['minute'] = ORDER_CUTOFF_MINUTE
            elif kind == 'weather':
                event['minute'] = 8 * 60
            elif kind == 'scan':
                event['minute'] = 9 * 60
            elif kind == 'capacity':
                receipts = [arrival_minutes[i][j] for j in range(len(skus)) if arrived_s[i, j] > 0]
                event['minute'] = max(receipts, default=9 * 60) + 10
    for event in events:
        if event['minute'] is None:
            raise ValueError(f"No shortage instant for {event['kind']} {event['date']} {event.get('sku')}")
        event.update(intraday.clock(event['date'], event['minute']))
        event['id'] = ':'.join((event['kind'], event.get('policy', 'plan'), event['date'], event.get('sku', 'all')))
    events.sort(key=lambda e: (e['at'], e['id']))

    first_week_cases = {
        policy: np.array(runs[policy]["per_sku"]["placed_cases"][:7], dtype=float).sum(axis=0)
        for policy in runs
    }
    card_skus = {s for card in cards for s in card.get("skus", [])}
    affected_skus = [s for i, s in enumerate(skus)
                     if abs(first_week_cases["scoop"][i] - first_week_cases["baseline"][i]) >= 1 or s in card_skus]

    def summary(policy: str, subset: list[str] | None = None) -> dict:
        rows = runs[policy]["daily"]
        if subset is None:
            dem = sum(r["demand"] for r in rows)
            shipped = sum(r["shipped"] for r in rows)
            lost = sum(r["lost"] for r in rows)
            lost_margin = sum(r["lost_margin"] for r in rows)
            pallets = [r["pallets"] for r in rows]
            pre_ship = [r["pallets_pre_ship"] for r in rows]
            ending = rows[-1]["on_hand"]
            ordered = sum(r["ordered_cases"] for r in rows)
            sku_days = int((np.array(runs[policy]["per_sku"]["lost"]) > 0).sum())
        else:
            ix = [skus.index(s) for s in subset]
            sku_run = runs[policy]["per_sku"]
            dem = float(demand.loc[start:end, subset].to_numpy().sum())
            shipped = float(np.array(sku_run["shipped"])[:, ix].sum())
            lost = float(np.array(sku_run["lost"])[:, ix].sum())
            lost_margin = float((np.array(sku_run["lost"])[:, ix] * margin.loc[subset].to_numpy()).sum())
            pallets = (np.array(sku_run["on_hand"])[:, ix] / upp.loc[subset].to_numpy()).sum(axis=1).tolist()
            pre_ship = (np.array(sku_run["pre_ship"])[:, ix] / upp.loc[subset].to_numpy()).sum(axis=1).tolist()
            ending = float(np.array(sku_run["on_hand"])[-1, ix].sum())
            ordered = int(np.array(sku_run["placed_cases"])[:, ix].sum())
            sku_days = int((np.array(sku_run["lost"])[:, ix] > 0).sum())
        return {
            "fill_rate": shipped / dem if dem else 1.0,
            "lost_units": lost,
            "lost_margin": lost_margin,
            "avg_pallets": float(np.mean(pallets)),
            "peak_pallets": float(max(pre_ship)),
            "days_over_capacity": int(sum(x > capacity + 1e-9 for x in pre_ship)),
            "stockout_sku_days": sku_days,
            "ending_on_hand": ending,
            "ordered_cases": int(ordered),
        }

    affected_summary = {policy: summary(policy, affected_skus) for policy in runs}
    affected_comparison = {
        "units_saved": affected_summary["baseline"]["lost_units"] - affected_summary["scoop"]["lost_units"],
        "pallet_difference": affected_summary["scoop"]["avg_pallets"] - affected_summary["baseline"]["avg_pallets"],
        "stockout_days_avoided": affected_summary["baseline"]["stockout_sku_days"] - affected_summary["scoop"]["stockout_sku_days"],
    }

    result = {
        "plan_id": pid, "start": start.isoformat(), "end": end.isoformat(), "days": days, "capacity_pallets": capacity,
        "skus": skus, "dates": dates,
        "products": [{"sku": s, "name": names[s], "brand": prod.loc[s, "brand"]} for s in skus],
        "demand": demand.loc[start:end].round(1).values.tolist(),
        "runs": runs, "intraday": intraday_data['intraday'], "events": events,
        "summary": {"scoop": summary("scoop"), "baseline": summary("baseline")},
        "affected_skus": affected_skus, "affected_summary": affected_summary,
        "affected_comparison": affected_comparison,
        "notes": {
            "baseline": "Simple rule: order up to 28-day average demand x (lead time + review days) x 1.25.",
            "lead_time": "New orders arrive after the supplier's mean lead time; orders placed late in the week may land after the played period.",
            "autopilot": "After the first week, Scoop refits cohort effects and places future orders automatically." if days > 7 else None,
        },
    }
    if not expectations.empty:
        forecast = expectations.pivot(index="date", columns="sku", values="expected_units")
        expected_grid = forecast.reindex(index=[date.fromisoformat(d) for d in dates], columns=skus).astype(object)
        result["expected"] = expected_grid.where(expected_grid.notna(), None).values.tolist()
        result["expected_source"] = {"run_id": forecast_run.id.iloc[0],
                                     "trained_through": str(forecast_run.trained_through.iloc[0])}
    _CACHE[key] = result
    return result
