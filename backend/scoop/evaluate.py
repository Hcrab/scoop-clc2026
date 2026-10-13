"""Offline evaluation on the synthetic world. Writes reports/evaluation.json and evaluation.md.

1. Forecast accuracy on the Apr-May 2026 holdout (model A) against simple baselines.
2. Detection: days from each planted trend's start to the first alarm, CUSUM vs a weekly
   check with the same false-alarm rate; false alarms in a twin world with no planted events.
3. Investigator: does its label match the planted cause?
4. Policy replay, Jun-Aug 2026: the DC re-simulated under three ordering policies on the
   same store orders.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .algorithms import cusum
from .algorithms.forecast import build_features, issued_daily_weather, calibrate_ratios
from .algorithms.groups import membership
from .algorithms.runs import CALIB_END, CALIB_START, MONITOR_END, MONITOR_START, artifacts
from .config import settings
from .db import get_setting, read_sql
from .monitoring import monitoring
from .planning import default_directions, detect, suggest_orders
from .synth.generate import null_orders

PLANTED_GROUPS = {"EV01": "family:fruit", "EV02": "feature:choc_coated", "EV03": "health:low_sugar"}
EVENT_ONSETS = {
    ("EV01", "Kowloon"): date(2026, 6, 22),
    ("EV01", "HK Island"): date(2026, 7, 6),
    ("EV01", "NT East"): date(2026, 7, 20),
    **{("EV02", d): date(2026, 6, 8) for d in ("Kowloon", "HK Island", "NT East", "NT West")},
}


def _wape(y: np.ndarray, f: np.ndarray) -> float:
    return float(np.abs(y - f).sum() / max(y.sum(), 1))


# --------------------------------------------------------------------------- 1. forecast


def forecast_accuracy() -> dict:
    art = artifacts()
    orders = read_sql("SELECT date, store_id, sku, ordered_units FROM store_orders WHERE date BETWEEN :a AND :b",
                      a=(CALIB_START - pd.Timedelta(days=35)).date(), b=CALIB_END.date())
    orders["date"] = pd.to_datetime(orders.date)
    exp = art.expectations[art.expectations.run == "A"]
    j = exp.merge(orders, on=["date", "store_id", "sku"])
    o = orders.sort_values("date").set_index(["store_id", "sku", "date"]).ordered_units
    naive = o.groupby(level=[0, 1]).shift(7).rename("naive")
    ma = o.groupby(level=[0, 1]).transform(lambda s: s.shift(1).rolling(28, min_periods=7).mean()).rename("ma28")
    j = j.merge(pd.concat([naive, ma], axis=1).reset_index(), on=["store_id", "sku", "date"], how="left").dropna()
    y = j.ordered_units.to_numpy()
    store_level = {
        "scoop_lightgbm": _wape(y, j["mean"].to_numpy()),
        "same_weekday_last_week": _wape(y, j.naive.to_numpy()),
        "moving_average_28d": _wape(y, j.ma28.to_numpy()),
        "interval_coverage_p10_p90": float(((y >= j.p10) & (y <= j.p90)).mean()),
    }
    # DC protection period: model vs moving-average x protection days
    r = calibrate_ratios(art.model_a, art.static, [date(2026,5,12),date(2026,5,16)])
    tot = read_sql("SELECT date, sku, SUM(ordered_units) AS u FROM store_orders GROUP BY date, sku")
    tot["date"] = pd.to_datetime(tot.date)
    ma_fc = []
    for row in r.itertuples():
        hist = tot[(tot.sku == row.sku) & (tot.date <= pd.Timestamp(row.issued)) & (tot.date > pd.Timestamp(row.issued) - pd.Timedelta(days=28))]
        ma_fc.append(hist.u.mean() * row.pdays)
    r["ma_fc"] = ma_fc
    lo, hi = np.quantile(art.ratio_values, [0.1, 0.9])
    dc = {
        "scoop_lightgbm": _wape(r.actual.to_numpy(), r.forecast.to_numpy()),
        "moving_average_28d": _wape(r.actual.to_numpy(), r.ma_fc.to_numpy()),
        "ratio_p10": float(lo),
        "ratio_p90": float(hi),
        "samples": int(len(r)),
        "heldout_interval_coverage": float(((r.actual >= r.forecast*lo)&(r.actual <= r.forecast*hi)).mean()),
        "heldout_issue_dates": ["2026-05-12", "2026-05-16"],
        "heldout_end": "2026-06-01",
    }
    return {"store_sku_day": store_level, "dc_protection_period": dc}


# --------------------------------------------------------------------------- 2. detection


def _first_alarm(series: pd.DataFrame, group: str, district: str, direction: str, h: float, after: pd.Timestamp) -> pd.Timestamp | None:
    s = series[(series.group == group) & (series.district == district)].sort_values("date")
    col = "s_up" if direction == "up" else "s_down"
    above = s[col] >= h
    hit = s[above & ~above.shift(1, fill_value=False) & (s.date >= after)]
    return hit.date.min() if len(hit) else None


def detection() -> dict:
    m = monitoring()
    cal = m.calibration
    weekly, thr = cusum.weekly_baseline_alarms(m.series, m.calib_resid, cal)
    exposed = {d: cusum.alarms_as_of(m.series, cal, d) for d in pd.date_range(MONITOR_START, MONITOR_END)}
    rows = []
    for (ev, district), onset in EVENT_ONSETS.items():
        group = PLANTED_GROUPS[ev]
        direction = "down" if ev == "EV02" else "up"
        on = pd.Timestamp(onset)
        c = _first_alarm(m.series, group, district, direction, cal.h, on)
        wk = weekly[(weekly.group == group) & (weekly.district == district) & (weekly.alarm_date >= on) & weekly[direction]]
        w = wk.alarm_date.min() if len(wk) else None
        gated_hit = next((d for d, af in exposed.items() if d >= on and ((af.group == group)&(af.district == district)&(af.direction == direction)&(af.first_cross >= on)&af.significant).any()), None)
        rows.append({
            "bh_gated_alarm": str(gated_hit.date()) if gated_hit is not None else None,
            "bh_gated_delay_days": int((gated_hit-on).days) if gated_hit is not None else None,
            "event": ev, "group": group, "district": district, "onset": str(onset),
            "cusum_alarm": str(c.date()) if c is not None else None,
            "cusum_delay_days": int((c - on).days) if c is not None else None,
            "weekly_alarm": str(w.date()) if w is not None else None,
            "weekly_delay_days": int((w - on).days) if w is not None else None,
        })
    det = pd.DataFrame(rows)
    both = det.dropna(subset=["cusum_delay_days", "weekly_delay_days"])

    # false alarms in a twin world without planted events
    art = artifacts()
    seed = int(get_setting("seed", "42"))
    null, null_weather = null_orders(seed)
    null["date"] = pd.to_datetime(null.date)
    null = null[(null.date >= CALIB_START) & (null.date <= MONITOR_END)]
    nw = null_weather.assign(date=pd.to_datetime(null_weather.date))
    exp_null = art.model_a.predict(build_features(art.static, pd.date_range(MONITOR_START, MONITOR_END), weather=issued_daily_weather(art.static, pd.date_range(MONITOR_START, MONITOR_END))))
    exp_all = pd.concat([art.expectations[art.expectations.run == "A"], exp_null.assign(run="B")], ignore_index=True)
    mem = membership(m.groups, list(art.static.products.sku))
    resid = cusum.residuals(null, exp_all, mem, m.store_district)
    live = resid[(resid.date >= MONITOR_START) & (resid.date <= MONITOR_END)]
    s = cusum.monitor(live, cal)
    gated = {d: cusum.alarms_as_of(s, cal, d) for d in pd.date_range(MONITOR_START, MONITOR_END)}
    gated_episodes = 0
    previous = set()
    for frame in gated.values():
        current = set(map(tuple, frame.loc[frame.significant, ["group", "district", "direction"]].to_numpy()))
        gated_episodes += len(current-previous)
        previous = current
    episodes = 0
    for _, part in s.groupby(["group", "district"]):
        for col in ("s_up", "s_down"):
            above = (part.sort_values("date")[col].to_numpy() >= cal.h).astype(int)
            episodes += int(((above[1:] - above[:-1]) == 1).sum() + above[0])
    charts = s.groupby(["group", "district"]).ngroups * 2
    days = (MONITOR_END - MONITOR_START).days + 1
    weekly_null = cusum.weekly_baseline_alarms(s, m.calib_resid, cal)[0]
    weekly_episodes = int(weekly_null.up.sum() + weekly_null.down.sum())

    # pooled weak-signal review of the planted low-sugar drift
    ls = m.series[m.series.group == "health:low_sugar"]
    pooled = ls.groupby("date").z.sum() / np.sqrt(ls.district.nunique())
    up, _ = cusum._run(pooled.to_numpy())
    pooled_hit = pooled.index[np.argmax(up >= cal.h)] if (up >= cal.h).any() else None
    district_hits = [_first_alarm(m.series, "health:low_sugar", d, "up", cal.h, MONITOR_START) for d in m.store_district.unique()]
    district_first = min([d for d in district_hits if d is not None], default=None)
    return {
        "threshold_h": cal.h, "k": cusum.K, "arl0_days": cusum.ARL0, "weekly_threshold_z": round(thr, 3),
        "events": rows,
        "raw_missed": sum(x["cusum_alarm"] is None for x in rows),
        "gated_missed": sum(x["bh_gated_alarm"] is None for x in rows),
        "mean_delay_cusum": float(both.cusum_delay_days.mean()) if len(both) else None,
        "mean_delay_weekly": float(both.weekly_delay_days.mean()) if len(both) else None,
        "null_world": {
            "charts": charts, "days": days, "cusum_false_alarm_episodes": episodes, "bh_gated_false_alarm_episodes": gated_episodes,
            "cusum_false_alarms_per_chart_per_90_days": round(episodes / charts * 90 / days, 3),
            "weekly_false_alarm_weeks": weekly_episodes,
        },
        "weak_signal_low_sugar": {
            "pooled_alarm": str(pooled_hit.date()) if pooled_hit is not None else None,
            "first_district_alarm": str(district_first.date()) if district_first is not None else None,
        },
    }


# --------------------------------------------------------------------------- 3. investigator


def investigator_accuracy(weeks: list[date]) -> dict:
    events = read_sql("SELECT * FROM ground_truth_events")
    m = monitoring()
    event_skus = {
        "EV01": set(m.group_by_id["family:fruit"].skus) & set(m.group_by_id["band:dairy:0"].skus),
        "EV02": set(m.group_by_id["feature:choc_coated"].skus),
        "EV03": set(m.group_by_id["health:low_sugar"].skus),
        "EV04": set(m.group_by_id["format:cone"].skus),
        "EV05": set(events[events.id == "EV05"].sku),
    }
    expected = dict(zip(events.id, events.expected_label))
    event_dir = {"EV01": "up", "EV02": "down", "EV03": "up", "EV04": "up", "EV05": "up"}
    rows = []
    for w in weeks:
        for f in detect(w):
            if f["kind"] != "significant" or f["classification"] == "mirror":
                continue
            g = set(m.group_by_id[f["group"]].skus)
            best, score = None, 0.0
            for ev, skus in event_skus.items():
                er = events[events.id == ev].iloc[0]
                observation = pd.Timestamp(w) - pd.Timedelta(days=1)
                end = pd.Timestamp(er.end_date) + pd.Timedelta(days=14) if er.end_date is not None else MONITOR_END
                applicable = [d for d in f["districts"] if d in er.districts and observation >= pd.Timestamp(EVENT_ONSETS.get((ev,d), er.start_date))]
                if not applicable or observation > end or pd.Timestamp(f["run_start"]) > end:
                    continue
                if event_dir[ev] != f["direction"]:
                    continue
                jac = len(g & skus) / len(g | skus)
                if jac > score:
                    best, score = ev, jac
            if best == "EV05" and score < 0.3:
                # a single-SKU event: match when the bulk-order store's district is flagged as concentrated
                pass
            matched = best if score >= 0.25 else None
            rows.append({"week": str(w), "finding": f["display"], "districts": f["districts"], "label": f["classification"],
                         "event": matched, "expected": expected.get(matched) if matched else "noise",
                         "correct": (expected.get(matched) == f["classification"]) if matched else None})
    df = pd.DataFrame(rows, columns=["week","finding","districts","label","event","expected","correct"])
    matched = df[df.event.notna()]
    return {
        "findings": rows,
        "total_exposed_nonmirror_findings": len(rows),
        "matched": int(len(matched)),
        "correct": int(matched.correct.sum()) if len(matched) else 0,
        "accuracy": float(matched.correct.mean()) if len(matched) else None,
        "unmatched_findings": int(df.event.isna().sum()),
    }


# --------------------------------------------------------------------------- 4. policy replay


_DETECT_CACHE: dict[date, list[dict]] = {}


def _weekly_directions(d: date) -> list[dict]:
    if d not in _DETECT_CACHE:
        _DETECT_CACHE[d] = default_directions(detect(d))
    return _DETECT_CACHE[d]


def replay(policy: str, *, buffer: float = 1.25, service_level: float | None = None,
           start: date = date(2026, 6, 1), end: date = date(2026, 8, 31)) -> dict:
    """Re-simulate the DC on the actual store orders. Lead times are the supplier means."""
    art = artifacts()
    prod = art.static.products.set_index("sku")
    skus = list(prod.index)
    orders = read_sql("SELECT date, sku, SUM(ordered_units) AS u FROM store_orders WHERE date BETWEEN :a AND :b GROUP BY date, sku",
                      a=start - timedelta(days=28), b=end)
    orders["date"] = pd.to_datetime(orders.date).dt.date
    demand = orders.pivot(index="date", columns="sku", values="u").reindex(columns=skus).fillna(0)
    inv0 = read_sql("SELECT sku, on_hand_units FROM node_inventory WHERE date = :d", d=start - timedelta(days=1)).set_index("sku").on_hand_units
    open_po = read_sql("""SELECT po.sku, po.cases * p.units_per_case AS units, po.received_date FROM purchase_orders po JOIN products p USING (sku)
                          WHERE po.order_date < :d AND (po.received_date IS NULL OR po.received_date >= :d)""", d=start)
    on_hand = inv0.reindex(skus).fillna(0).astype(float)
    arrivals: dict[date, pd.Series] = {}
    for r in open_po.itertuples():
        arrivals.setdefault(r.received_date, pd.Series(0.0, index=skus))[r.sku] += r.units
    pipeline = open_po.groupby("sku").units.sum().reindex(skus).fillna(0).astype(float)
    capacity = float(read_sql("SELECT capacity_pallets FROM nodes WHERE id = 'DC1'").capacity_pallets.iloc[0])
    upp = (prod.units_per_case * prod.cases_per_pallet).reindex(skus)
    margin = (prod.price_hkd - prod.cost_hkd).reindex(skus)
    lost_units = shipped_total = demand_total = lost_margin = 0.0
    pallets, over_days, n_pos = [], 0, 0
    pre_ship_pallets = []
    directions: list[dict] = []
    d = start
    while d <= end:
        if d in arrivals:
            on_hand += arrivals[d]
            pipeline -= arrivals[d]
        pre_ship_pallets.append(float((on_hand / upp).sum()))
        if policy == "scoop_full" and d.weekday() == 0:
            directions = _weekly_directions(d)
        due = list(prod.index[prod.order_weekday == d.weekday()])
        plan = None
        if policy != "history" and due:
            pos = pd.DataFrame({"sku": skus, "on_hand_units": on_hand.round().astype(int).to_numpy(), "on_order": pipeline.round().astype(int).to_numpy()})
            plan = suggest_orders(d, directions, service_level=service_level, position=pos, only_due=True, pending_arrivals=arrivals).set_index("sku")
        dem = demand.loc[d]
        ship = np.minimum(on_hand, dem)
        lost = dem - ship
        on_hand -= ship
        lost_units += lost.sum()
        lost_margin += float((lost * margin).sum())
        shipped_total += ship.sum()
        demand_total += dem.sum()
        p = float((on_hand / upp).sum())
        pallets.append(p)
        over_days += p > capacity
        for sku in due:
            lead = int(prod.loc[sku, "lead_time_days"])
            if policy == "history":
                hist = demand.loc[d - timedelta(days=28): d - timedelta(days=1), sku].mean()
                need = max(0.0, hist * (lead + int(prod.loc[sku, "review_days"])) * buffer - (on_hand[sku] + ship[sku]) - pipeline[sku])
                cases = int(np.ceil(need / prod.loc[sku, "units_per_case"]))
                cases = max(cases, int(prod.loc[sku, "moq_cases"])) if cases > 0 else 0
            else:
                cases = int(plan.loc[sku, "final_cases"])
            if cases:
                units = cases * float(prod.loc[sku, "units_per_case"])
                arrivals.setdefault(d + timedelta(days=lead), pd.Series(0.0, index=skus))[sku] += units
                pipeline[sku] += units
                n_pos += 1
        d += timedelta(days=1)
    label = f"history x{buffer:.2f}" if policy == "history" else f"{policy} @ {'CR' if service_level is None else f'{service_level:.0%}'}"
    return {
        "policy": policy, "label": label, "buffer": buffer if policy == "history" else None, "service_level": service_level,
        "fill_rate": round(shipped_total / demand_total, 4),
        "lost_units": int(lost_units),
        "lost_margin_hkd": round(lost_margin, 0),
        "avg_pallets": round(float(np.mean(pallets)), 1),
        "max_pallets": round(float(np.max(pallets)), 1),
        "peak_pallets_before_shipping": round(float(np.max(pre_ship_pallets)),1),
        "days_over_capacity_before_shipping": int(sum(p > capacity for p in pre_ship_pallets)),
        "days_over_capacity": int(over_days),
        "capacity_pallets": capacity,
        "purchase_orders": n_pos,
    }


# --------------------------------------------------------------------------- entry point


def run() -> dict:
    t0 = time.time()
    weeks = [x.date() for x in pd.date_range("2026-06-29", "2026-08-10", freq="W-MON")]
    out = {"generated_seconds": None}
    out["forecast"] = forecast_accuracy()
    print("forecast done", round(time.time() - t0))
    out["detection"] = detection()
    print("detection done", round(time.time() - t0))
    out["investigator"] = investigator_accuracy(weeks)
    print("investigator done", round(time.time() - t0))
    runs = [replay("history", buffer=b) for b in (1.0, 1.15, 1.25, 1.4)]
    runs += [replay("scoop_forecast", service_level=sl) for sl in (None, 0.92)]
    runs += [replay("scoop_full", service_level=sl) for sl in (None, 0.85, 0.92, 0.96)]
    out["replay"] = runs
    print("replay done", round(time.time() - t0))
    out["generated_seconds"] = round(time.time() - t0, 1)
    settings.reports_dir.mkdir(exist_ok=True)
    (settings.reports_dir / "evaluation.json").write_text(json.dumps(out, indent=2, default=str))
    (settings.reports_dir / "evaluation.md").write_text(markdown(out))
    return out


def markdown(r: dict) -> str:
    f = r["forecast"]
    d = r["detection"]
    inv = r["investigator"]
    lines = ["# Scoop evaluation (synthetic data)", "",
             "See [algorithm assumptions and limitations](../docs/ALGORITHM_NOTES.md). All numbers come from `python -m scoop.evaluate` on the synthetic world (seed 42). They show the method works on data with known answers; they are not claims about real PARKnSHOP or LOGFLOWS operations.", "",
             "## 1. Forecast accuracy (holdout Apr-May 2026)", "",
             "| Level | Scoop (LightGBM) | Same weekday last week | 28-day moving average |", "|---|---|---|---|",
             f"| Store x SKU x day, WAPE | {f['store_sku_day']['scoop_lightgbm']:.1%} | {f['store_sku_day']['same_weekday_last_week']:.1%} | {f['store_sku_day']['moving_average_28d']:.1%} |",
             f"| DC protection period, WAPE | {f['dc_protection_period']['scoop_lightgbm']:.1%} | - | {f['dc_protection_period']['moving_average_28d']:.1%} |", "",
             f"Daily p10-p90 interval coverage: {f['store_sku_day']['interval_coverage_p10_p90']:.1%} (target 80%).", "",
             "## 2. Detection of planted trends", "",
             f"CUSUM k = {d['k']}, threshold h = {d['threshold_h']} (bootstrap ARL target {d['arl0_days']} days; empirical approximation, no exact guarantee). Raw threshold alarms and BH-gated exposures are separately recorded in JSON.", "",
             "| Event | Group | District | Starts | Raw CUSUM | Days | BH-gated | Days | Weekly check | Days |", "|---|---|---|---|---|---|---|---|---|---|"]
    for e in d["events"]:
        lines.append(f"| {e['event']} | {e['group']} | {e['district']} | {e['onset']} | {e['cusum_alarm'] or 'none'} | {e['cusum_delay_days'] if e['cusum_delay_days'] is not None else '-'} | {e['bh_gated_alarm'] or 'none'} | {e['bh_gated_delay_days'] if e['bh_gated_delay_days'] is not None else '-'} | {e['weekly_alarm'] or 'none'} | {e['weekly_delay_days'] if e['weekly_delay_days'] is not None else '-'} |")
    lines += ["", f"Missed trend/district pairs: raw {d['raw_missed']}/{len(d['events'])}; BH-gated {d['gated_missed']}/{len(d['events'])}.", f"Held-out protection interval coverage: {f['dc_protection_period']['heldout_interval_coverage']:.1%} across {f['dc_protection_period']['samples']} windows. Calibration and validation outcomes do not overlap."]
    nw = d["null_world"]
    lines += ["", f"Mean delay: CUSUM {d['mean_delay_cusum']:.1f} days vs weekly check {d['mean_delay_weekly']:.1f} days." if d['mean_delay_cusum'] is not None and d['mean_delay_weekly'] is not None else "",
              "", f"False alarms in a twin world with no planted events: {nw['cusum_false_alarm_episodes']} alarm episodes over {nw['charts']} charts x {nw['days']} days "
              f"= {nw['cusum_false_alarms_per_chart_per_90_days']} per chart per 90 days; actual BH-gated false-alarm episodes: {nw['bh_gated_false_alarm_episodes']}.", "",
              f"Weak signal (low-sugar drift, +12% over three months): pooled network review alarms on {d['weak_signal_low_sugar']['pooled_alarm']}; first single-district alarm {d['weak_signal_low_sugar']['first_district_alarm']}.", "",
              "## 3. Investigator labels", "",
              f"{inv['correct']} of {inv['matched']} findings that match a planted event got the right label" + (f" ({inv['accuracy']:.0%})." if inv['accuracy'] is not None else "."), "",
              "| Week | Finding | Districts | Label | Planted event | Expected |", "|---|---|---|---|---|---|"]
    for x in inv["findings"]:
        lines.append(f"| {x['week']} | {x['finding']} | {', '.join(x['districts'])} | {x['label']} | {x['event'] or '-'} | {x['expected']} |")
    lines += ["", "## 4. Policy replay, Jun-Aug 2026", "", "| Policy | Fill rate | Lost units | Lost margin (HKD) | Avg closing pallets | Max closing pallets | Days over closing capacity | Peak before shipping | Days over before shipping | POs |", "|---|---|---|---|---|---|---|---|---|---|"]
    for p in r["replay"]:
        lines.append(f"| {p['label']} | {p['fill_rate']:.2%} | {p['lost_units']:,} | {p['lost_margin_hkd']:,.0f} | {p['avg_pallets']} | {p['max_pallets']} | {p['days_over_capacity']} | {p['peak_pallets_before_shipping']} | {p['days_over_capacity_before_shipping']} | {p['purchase_orders']} |")
    lines += ["", "history xB = 28-day moving average x (lead + 7 days) x buffer B (the policy that produced the synthetic history uses 1.25). "
              "scoop_forecast = order-up-to on the LightGBM protection-period forecast. scoop_full = scoop_forecast plus the weekly CUSUM findings with the AI draft directions accepted. "
              "@ CR = newsvendor critical ratio per SKU; @ 92% = fixed service level. Compare policies at similar average pallets: the question is how much stock buys how much fill rate.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    res = run()
    print(json.dumps({k: v for k, v in res.items() if k != "investigator"}, indent=1, default=str)[:4000])
