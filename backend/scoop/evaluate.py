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
from .algorithms.forecast import build_features, issued_daily_weather, calibrate_ratios, DemandModel
from .algorithms.groups import membership
from .algorithms.runs import CALIB_END, CALIB_START, MONITOR_END, MONITOR_START, artifacts, month_start, month_end, version_for, TRAIN_START, _cache_dir, _load, _save
from .config import settings
from .db import get_setting, read_sql, session_scope
from .models import ModelRun
from .monitoring import monitoring
from .planning import default_directions, detect, suggest_orders, active_directions
from .synth.generate import null_orders

PLANTED_GROUPS = {"EV01": "family:fruit", "EV02": "feature:choc_coated", "EV03": "health:low_sugar"}
EVENT_ONSETS = {
    ("EV01", "Kowloon"): date(2026, 6, 22),
    ("EV01", "HK Island"): date(2026, 7, 6),
    ("EV01", "NT East"): date(2026, 7, 20),
    **{("EV02", d): date(2026, 6, 8) for d in ("Kowloon", "HK Island", "NT East", "NT West")},
    **{("EV03", d): date(2026,6,1) for d in ("Kowloon", "HK Island", "NT East", "NT West")},
}


def _wape(y: np.ndarray, f: np.ndarray) -> float:
    return float(np.abs(y - f).sum() / max(y.sum(), 1))


# --------------------------------------------------------------------------- 1. forecast


def _pinball(y, prediction, quantile):
    error = np.asarray(y)-np.asarray(prediction)
    return float(np.maximum(quantile*error,(quantile-1)*error).mean())


def forecast_accuracy() -> dict:
    art = artifacts()
    orders = read_sql("SELECT date, store_id, sku, ordered_units FROM store_orders WHERE date BETWEEN :a AND :b",
                      a=(CALIB_START-pd.Timedelta(days=35)).date(),b=MONITOR_END.date())
    orders["date"] = pd.to_datetime(orders.date)
    history = orders.sort_values("date").set_index(["store_id","sku","date"]).ordered_units
    naive = history.groupby(level=[0,1]).shift(7).rename("naive")
    ma = history.groupby(level=[0,1]).transform(lambda s:s.shift(1).rolling(28,min_periods=7).mean()).rename("ma28")
    joined = art.expectations.merge(orders,on=["date","store_id","sku"]).merge(
        pd.concat([naive,ma],axis=1).reset_index(),on=["date","store_id","sku"]).dropna()
    def daily_metrics(frame):
        y=frame.ordered_units.to_numpy()
        return {"scoop_lightgbm":_wape(y,frame['mean'].to_numpy()),
                "same_weekday_last_week":_wape(y,frame.naive.to_numpy()),
                "moving_average_28d":_wape(y,frame.ma28.to_numpy()),
                "interval_coverage_p10_p90":float(((y>=frame.p10)&(y<=frame.p90)).mean()),
                "pinball_p10":_pinball(y,frame.p10,.1),"pinball_p90":_pinball(y,frame.p90,.9),
                "samples":len(frame)}
    rolling=[]
    totals=orders.groupby(["date","sku"]).ordered_units.sum().rename("units").reset_index()
    protection=[]
    for effective in pd.date_range(CALIB_START,MONITOR_END,freq="MS"):
        monthly=art.run_for(effective.date())
        frame=joined[joined.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        dates=[d.date() for d in pd.date_range(effective,min(pd.Timestamp(MONITOR_END),pd.Timestamp(month_end(effective.date())))-pd.Timedelta(days=16),freq="7D")]
        ratios=calibrate_ratios(monthly.model,art.static,dates)
        lo,med,hi=np.quantile(monthly.ratio_values,[.1,.5,.9])
        ratios['lo'],ratios['med'],ratios['hi']=ratios.forecast*lo,ratios.forecast*med,ratios.forecast*hi
        ratios['model_version']=monthly.model.version
        ma_values=[]
        for row in ratios.itertuples():
            past=totals[(totals.sku==row.sku)&(totals.date<=pd.Timestamp(row.issued))&(totals.date>pd.Timestamp(row.issued)-pd.Timedelta(days=28))]
            ma_values.append(past.units.mean()*row.pdays)
        ratios['ma_fc']=ma_values
        protection.append(ratios)
        rolling.append({**monthly.metadata,"store_sku_day":daily_metrics(frame),
            "protection_wape":_wape(ratios.actual,ratios.forecast),
            "protection_interval_coverage":float(((ratios.actual>=ratios.lo)&(ratios.actual<=ratios.hi)).mean()),
            "protection_pinball_p10":_pinball(ratios.actual,ratios.lo,.1),
            "protection_pinball_p50":_pinball(ratios.actual,ratios.med,.5),
            "protection_pinball_p90":_pinball(ratios.actual,ratios.hi,.9),
            "protection_test_issues":[d.isoformat() for d in dates],"protection_test_samples":len(ratios)})
    windows=pd.concat(protection,ignore_index=True)
    lo,hi=np.quantile(art.ratio_values,[.1,.9])
    dc={"scoop_lightgbm":_wape(windows.actual,windows.forecast),
        "moving_average_28d":_wape(windows.actual,windows.ma_fc),"ratio_p10":float(lo),"ratio_p90":float(hi),
        "samples":len(windows),"heldout_interval_coverage":float(((windows.actual>=windows.lo)&(windows.actual<=windows.hi)).mean()),
        "heldout_issue_dates":sorted({str(d) for d in windows.issued}),"heldout_end":str(MONITOR_END.date()),
        "pinball_p10":_pinball(windows.actual,windows.lo,.1),"pinball_p50":_pinball(windows.actual,windows.med,.5),
        "pinball_p90":_pinball(windows.actual,windows.hi,.9)}
    return {"store_sku_day":daily_metrics(joined[joined.date<=CALIB_END]),
            "dc_protection_period":dc,"rolling_origin":rolling}


# --------------------------------------------------------------------------- 2. detection


def _first_alarm(series: pd.DataFrame, group: str, district: str, direction: str, h: float, after: pd.Timestamp) -> pd.Timestamp | None:
    s = series[(series.group == group) & (series.district == district)].sort_values("date")
    col = "s_up" if direction == "up" else "s_down"
    above = s[col] >= h
    hit = s[above & ~above.shift(1, fill_value=False) & (s.date >= after)]
    return hit.date.min() if len(hit) else None


def _monthly_alarm_tables(series,calibrations):
    tables={}
    for day in pd.date_range(MONITOR_START,MONITOR_END):
        version=version_for(day)
        current=series[(series.date>=pd.Timestamp(month_start(day)))&(series.date<=day)]
        tables[day]=cusum.alarms_as_of(current,calibrations[version],day)
    return tables


def _episode_counts(series,calibrations,tables):
    raw=0
    for effective in pd.date_range(MONITOR_START,MONITOR_END,freq="MS"):
        current=series[series.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        cal=calibrations[version_for(effective)]
        for _,part in current.groupby(["group","district"]):
            for col in ('s_up','s_down'):
                above=(part.sort_values('date')[col].to_numpy()>=cal.h).astype(int)
                raw+=int(np.sum(np.diff(above)==1)+above[0])
    gated=0
    previous=set()
    for day,table in tables.items():
        if day.day==1:
            previous=set()
        current=set(map(tuple,table.loc[table.significant,['group','district','direction']].to_numpy()))
        gated+=len(current-previous)
        previous=current
    return raw,gated


def _null_monthly_monitoring(art,m):
    """Train July/August in the null world too, avoiding a shifted-model fake null."""
    import pickle
    path=_cache_dir()/'null-monitoring-v1.pkl'
    if path.exists():
        return pickle.loads(path.read_bytes())
    null,_=null_orders(int(get_setting('seed','42')))
    null['date']=pd.to_datetime(null.date)
    predicted=[]
    for effective in pd.date_range('2026-05-01',MONITOR_END,freq='MS'):
        if effective<=pd.Timestamp('2026-06-01'):
            model=art.run_for(effective.date()).model
        else:
            name=version_for(effective).replace('M','N',1)
            model=_load(name)
            if model is None:
                model=DemandModel.train(art.static,TRAIN_START,effective.date()-timedelta(days=1),orders=null,train_quantiles=False)
                model.version=name
                _save(model,name)
        dates=pd.date_range(effective,month_end(effective.date()))
        features=build_features(art.static,dates,weather=issued_daily_weather(art.static,dates))
        predicted.append(model.predict(features,mean_only=True))
    expected=pd.concat(predicted,ignore_index=True)
    residual=cusum.residuals(null,expected,membership(m.groups,list(art.static.products.sku)),m.store_district)
    calibrations,cal_frames,rows={},{},[]
    for effective in pd.date_range(MONITOR_START,MONITOR_END,freq='MS'):
        calibration_end=effective-pd.Timedelta(days=1)
        frame=residual[residual.date.between(pd.Timestamp(month_start(calibration_end)),calibration_end)]
        cal=cusum.calibrate(frame)
        live=residual[residual.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        rows.append(cusum.monitor(live,cal))
        calibrations[version_for(effective)],cal_frames[version_for(effective)]=cal,frame
    result=(pd.concat(rows,ignore_index=True),calibrations,cal_frames)
    path.write_bytes(pickle.dumps(result))
    return result


_EXPOSED_FOR_EVALUATION = {}


def detection() -> dict:
    global _EXPOSED_FOR_EVALUATION
    m=monitoring()
    exposed=_monthly_alarm_tables(m.series,m.calibrations)
    _EXPOSED_FOR_EVALUATION = exposed
    weekly_rows=[]
    thresholds={}
    for effective in pd.date_range(MONITOR_START,MONITOR_END,freq='MS'):
        version=version_for(effective)
        current=m.series[m.series.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        weekly,threshold=cusum.weekly_baseline_alarms(current,m.calibration_frames[version],m.calibrations[version])
        weekly.alarm_date=weekly.alarm_date.clip(upper=pd.Timestamp(month_end(effective.date())))
        weekly_rows.append(weekly)
        thresholds[version]=threshold
    weekly=pd.concat(weekly_rows,ignore_index=True)
    rows=[]
    for (event,district),onset in EVENT_ONSETS.items():
        group=PLANTED_GROUPS[event]
        direction='down' if event=='EV02' else 'up'
        on=pd.Timestamp(onset)
        raw=[]
        for effective in pd.date_range(MONITOR_START,MONITOR_END,freq='MS'):
            subset=m.series[m.series.date.between(effective,pd.Timestamp(month_end(effective.date())))]
            hit=_first_alarm(subset,group,district,direction,m.calibrations[version_for(effective)].h,on)
            if hit is not None:
                raw.append(hit)
        c=min(raw) if raw else None
        wk=weekly[(weekly.group==group)&(weekly.district==district)&(weekly.alarm_date>=on)&weekly[direction]]
        w=wk.alarm_date.min() if len(wk) else None
        gated=next((d for d,table in exposed.items() if d>=on and
            ((table.group==group)&(table.district==district)&(table.direction==direction)&
             (table.first_cross>=on)&table.significant).any()),None)
        rows.append({'event':event,'target_type':'weak' if event=='EV03' else 'strong','group':group,
            'district':district,'onset':str(onset),'cusum_alarm':str(c.date()) if c is not None else None,
            'cusum_delay_days':int((c-on).days) if c is not None else None,
            'weekly_alarm':str(w.date()) if w is not None else None,'weekly_delay_days':int((w-on).days) if w is not None else None,
            'bh_gated_alarm':str(gated.date()) if gated is not None else None,
            'bh_gated_delay_days':int((gated-on).days) if gated is not None else None,
            'late_over_14_days':bool(gated is not None and (gated-on).days>14)})
    both=pd.DataFrame(rows).dropna(subset=['cusum_delay_days','weekly_delay_days'])
    art=artifacts()
    null_series,null_cal,null_frames=_null_monthly_monitoring(art,m)
    null_tables=_monthly_alarm_tables(null_series,null_cal)
    episodes,gated_episodes=_episode_counts(null_series,null_cal,null_tables)
    weekly_null=0
    for effective in pd.date_range(MONITOR_START,MONITOR_END,freq='MS'):
        version=version_for(effective)
        part=null_series[null_series.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        weekly_cal,_=cusum.weekly_baseline_alarms(part,null_frames[version],null_cal[version])
        weekly_null+=int(weekly_cal.up.sum()+weekly_cal.down.sum())
    charts=null_series.groupby(['group','district']).ngroups*2
    days=(MONITOR_END-MONITOR_START).days+1
    ls=m.series[m.series.group=='health:low_sugar']
    pooled_hits=[]
    for effective in pd.date_range(MONITOR_START,MONITOR_END,freq='MS'):
        part=ls[ls.date.between(effective,pd.Timestamp(month_end(effective.date())))]
        pooled=part.groupby('date').z.sum()/np.sqrt(part.district.nunique())
        up,_=cusum._run(pooled.to_numpy())
        hit=pooled.index[np.argmax(up>=m.calibrations[version_for(effective)].h)] if (up>=m.calibrations[version_for(effective)].h).any() else None
        if hit is not None:
            pooled_hits.append(hit)
    raw_low=[pd.Timestamp(r['cusum_alarm']) for r in rows if r['event']=='EV03' and r['cusum_alarm']]
    return {'threshold_h':m.calibration.h,'k':cusum.K,'arl0_days':cusum.ARL0,
        'weekly_threshold_z':round(thresholds[version_for(MONITOR_START)],3),
        'monthly_thresholds':{version:{'h':cal.h,'weekly_z':thresholds[version],
            'calibration_start':str(m.calibration_frames[version].date.min().date()),
            'calibration_end':str(m.calibration_frames[version].date.max().date())} for version,cal in m.calibrations.items()},
        'events':rows,'target_denominator':len(rows),'strong_target_denominator':7,'weak_target_denominator':4,
        'raw_missed':sum(r['cusum_alarm'] is None for r in rows),'gated_missed':sum(r['bh_gated_alarm'] is None for r in rows),
        'late_gated_detections':sum(r['late_over_14_days'] for r in rows),
        'strong_gated_missed':sum(r['bh_gated_alarm'] is None for r in rows if r['target_type']=='strong'),
        'weak_gated_missed':sum(r['bh_gated_alarm'] is None for r in rows if r['target_type']=='weak'),
        'paired_detected_targets':len(both),
        'mean_delay_cusum':float(both.cusum_delay_days.mean()) if len(both) else None,
        'mean_delay_weekly':float(both.weekly_delay_days.mean()) if len(both) else None,
        'mean_delay_bh_gated':float(np.mean([r['bh_gated_delay_days'] for r in rows if r['bh_gated_delay_days'] is not None])) if any(r['bh_gated_alarm'] for r in rows) else None,
        'null_world':{'charts':charts,'days':days,'cusum_false_alarm_episodes':episodes,
            'bh_gated_false_alarm_episodes':gated_episodes,'cusum_false_alarms_per_chart_per_90_days':round(episodes/charts*90/days,3),
            'weekly_false_alarm_weeks':weekly_null,'monthly_models_trained_on_null_demand':True},
        'weak_signal_low_sugar':{'pooled_alarm':str(min(pooled_hits).date()) if pooled_hits else None,
            'first_district_alarm':str(min(raw_low).date()) if raw_low else None,'status':'exploratory_not_FDR'}}


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
    weak_rows = []
    random_rows = []
    rng = np.random.default_rng(17)
    for w in weeks:
        found = detect(w)
        observation = pd.Timestamp(w)-pd.Timedelta(days=1)
        for finding in found:
            if finding["kind"]=="weak":
                later=any(((table.group==finding["group"])&table.district.isin(finding["districts"])&
                    (table.direction==finding["direction"])&table.significant).any() for day,table in _EXPOSED_FOR_EVALUATION.items()
                    if observation<day<=observation+pd.Timedelta(days=14))
                weak_rows.append({"week":str(w),"group":finding["group"],"direction":finding["direction"],
                    "followup_complete":observation+pd.Timedelta(days=14)<=MONITOR_END,
                    "later_bh_confirmed":bool(later) if observation+pd.Timedelta(days=14)<=MONITOR_END else None})
        candidates=[(group.id,direction) for group in m.groups for direction in ("up","down")]
        for index in rng.choice(len(candidates),size=min(10,len(candidates)),replace=False):
            group,direction=candidates[int(index)]
            later=any(((table.group==group)&(table.direction==direction)&table.significant).any()
                      for day,table in _EXPOSED_FOR_EVALUATION.items() if observation<day<=observation+pd.Timedelta(days=14))
            random_rows.append({"week":str(w),"group":group,"direction":direction,
                "followup_complete":observation+pd.Timedelta(days=14)<=MONITOR_END,
                "later_bh_confirmed":bool(later) if observation+pd.Timedelta(days=14)<=MONITOR_END else None})
        for f in found:
            if f["kind"] != "significant":
                continue
            g = set(m.group_by_id[f["group"]].skus)
            best, score = None, 0.0
            for ev, skus in event_skus.items():
                er = events[events.id == ev].iloc[0]
                observation = pd.Timestamp(w) - pd.Timedelta(days=1)
                event_end = pd.Timestamp(er.end_date) if er.end_date is not None else MONITOR_END
                end = event_end + pd.Timedelta(days=14) if er.end_date is not None else MONITOR_END
                applicable = [d for d in f["districts"] if d in er.districts and observation >= pd.Timestamp(EVENT_ONSETS.get((ev,d), er.start_date))]
                if not applicable or observation > end or pd.Timestamp(f["run_start"]) > event_end:
                    continue
                if event_dir[ev] != f["direction"]:
                    continue
                jac = len(g & skus) / len(g | skus)
                if ev=="EV05":
                    concentration = next((c for c in f.get('checks',[]) if c['name']=='concentration'),None)
                    evidence = concentration['data'] if concentration else {}
                    if (concentration and concentration['passed'] and evidence.get('sku') in skus
                        and evidence.get('date') and pd.Timestamp(er.start_date)<=pd.Timestamp(evidence['date'])<=event_end):
                        jac = 1.0  # exact measured store-day/SKU anomaly, not arbitrary group overlap
                if jac > score:
                    best, score = ev, jac
            matched = best if score >= 0.25 else None
            rows.append({"week": str(w), "finding": f["display"], "districts": f["districts"], "label": f["classification"],
                         "event": matched, "expected": expected.get(matched) if matched else "noise",
                         "correct": (expected.get(matched) == f["classification"]) if matched else None})
    df = pd.DataFrame(rows, columns=["week","finding","districts","label","event","expected","correct"])
    matched = df[df.event.notna()]
    return {
        "findings": rows,
        "total_exposed_nonmirror_findings": int((df.label!='mirror').sum()),
        "total_exposed_significant_findings":len(rows),
        "matched": int(len(matched)),
        "correct": int(matched.correct.sum()) if len(matched) else 0,
        "accuracy": float(matched.correct.mean()) if len(matched) else None,
        "unmatched_findings": int(df.event.isna().sum()),
        "planner_actionable":int((df.label=='persistent').sum()),
        "neutral_fraction":float((df.label!='persistent').mean()) if len(df) else None,
        "true_trend_matched_findings":int((matched.expected=='persistent').sum()),
        "true_trend_labeled_persistent":int(((matched.expected=='persistent')&(matched.label=='persistent')).sum()),
        "temporary_matched_findings":int((matched.expected!='persistent').sum()),
        "temporary_neutralized":int(((matched.expected!='persistent')&(matched.label!='persistent')).sum()),
        "weak_review_followup":{"horizon_days":14,"exposed_weak_candidates":weak_rows,
            "later_bh_confirmed":sum(x['later_bh_confirmed'] is True for x in weak_rows),
            "denominator":sum(x["followup_complete"] for x in weak_rows),
            "censored_candidates":sum(not x["followup_complete"] for x in weak_rows),
            "random_comparison_later_bh_confirmed":sum(x['later_bh_confirmed'] is True for x in random_rows),
            "random_comparison_denominator":sum(x["followup_complete"] for x in random_rows),
            "scope_note":"Only complete 14-day followups enter the denominators. Weak followups use their reviewed districts; random candidates use all districts and are a rough exploratory comparator, not a significance test"},
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
    frozen_mean = demand.loc[start-timedelta(days=28):start-timedelta(days=1)].mean()
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
            received = arrivals.pop(d)
            on_hand += received
            pipeline -= received
        pre_ship_pallets.append(float((on_hand / upp).sum()))
        if policy == "scoop_full" and d.day == 1:
            directions = []  # the shared monthly model absorbs prior evidence; reset temporary factors
        if policy == "scoop_full" and d.weekday() == 0:
            directions = _weekly_directions(d)
        due = list(prod.index[prod.order_weekday == d.weekday()])
        plan = None
        if policy not in ("history","fixed_reorder_point") and due:
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
            if policy == "fixed_reorder_point":
                position = on_hand[sku]+ship[sku]+pipeline[sku]
                reorder_point = frozen_mean[sku]*(lead+int(prod.loc[sku,"review_days"]))*buffer
                fixed_units = frozen_mean[sku]*int(prod.loc[sku,"review_days"])
                cases = int(np.ceil(fixed_units/prod.loc[sku,"units_per_case"])) if position<=reorder_point else 0
                cases = max(cases,int(prod.loc[sku,"moq_cases"])) if cases>0 else 0
            elif policy == "history":
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
    label = (f"history x{buffer:.2f}" if policy == "history" else f"fixed reorder point x{buffer:.2f}" if policy=="fixed_reorder_point" else f"{policy} @ {'CR' if service_level is None else f'{service_level:.0%}'}")
    return {
        "policy": policy, "label": label, "buffer": buffer if policy in ("history","fixed_reorder_point") else None, "service_level": service_level,
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
        "fixed_baseline_reference": {"start":str(start-timedelta(days=28)),"end":str(start-timedelta(days=1)),"reorder_point":"frozen_mean*(lead+review)*buffer","order_quantity":"frozen_mean*review, case-rounded and MOQ"} if policy=="fixed_reorder_point" else None,
    }


# --------------------------------------------------------------------------- entry point


def run() -> dict:
    t0 = time.time()
    weeks = [x.date() for x in pd.date_range("2026-06-01", "2026-08-31", freq="W-MON")]
    _DETECT_CACHE.clear()
    out = {"generated_seconds": None,"seed":int(get_setting("seed","42")),
           "model_lifecycle":"monthly shared frozen versions with previous-month out-of-sample error calibration"}
    out["forecast"] = forecast_accuracy()
    print("forecast done", round(time.time() - t0))
    out["detection"] = detection()
    print("detection done", round(time.time() - t0))
    out["investigator"] = investigator_accuracy(weeks)
    print("investigator done", round(time.time() - t0))
    runs = [replay("fixed_reorder_point",buffer=1.25)]
    runs += [replay("history", buffer=b) for b in (1.0, 1.15, 1.25, 1.4)]
    runs += [replay("scoop_forecast", service_level=sl) for sl in (None, 0.92)]
    runs += [replay("scoop_full", service_level=sl) for sl in (None, 0.85, 0.92, 0.96)]
    out["replay"] = runs
    out["monthly_models"] = [artifacts().run_for(d.date()).metadata for d in pd.date_range(MONITOR_START,MONITOR_END,freq="MS")]
    out["weak_reviews"] = monitoring().review_log
    print("replay done", round(time.time() - t0))
    with session_scope() as session:
        for row in out['forecast']['rolling_origin']:
            model_run = session.get(ModelRun,row['version'])
            if model_run is not None:
                model_run.metrics = {"evaluation_kind":"monthly_rolling_origin",
                    "store_sku_day":row['store_sku_day'],"protection_wape":row['protection_wape'],
                    "protection_interval_coverage":row['protection_interval_coverage'],
                    "protection_test_samples":row['protection_test_samples']}
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
             "## 1. Forecast accuracy (monthly rolling origins Apr-Aug 2026)", "",
             "| Level | Scoop (LightGBM) | Same weekday last week | 28-day moving average |", "|---|---|---|---|",
             f"| Store x SKU x day (Apr-May), WAPE | {f['store_sku_day']['scoop_lightgbm']:.1%} | {f['store_sku_day']['same_weekday_last_week']:.1%} | {f['store_sku_day']['moving_average_28d']:.1%} |",
             f"| DC protection period (Apr-Aug), WAPE | {f['dc_protection_period']['scoop_lightgbm']:.1%} | - | {f['dc_protection_period']['moving_average_28d']:.1%} |", "",
             f"Daily p10-p90 interval coverage: {f['store_sku_day']['interval_coverage_p10_p90']:.1%} (target 80%).", "",
             "## 2. Detection of planted trends", "",
             "A shared model retrains at each month boundary and CUSUM starts at zero. The table includes seven strong trend/district targets and four weak low-sugar targets. Missing alarms are counted through August 31; alarms over 14 days late are separately reported. Full monthly cutoff, calibration and threshold metadata are in JSON.", "",
             f"CUSUM k = {d['k']}, initial June threshold h = {d['threshold_h']} (bootstrap ARL target {d['arl0_days']} days; empirical approximation, no exact guarantee). Raw threshold alarms and BH-gated exposures are separately recorded in JSON.", "",
             "| Event | Group | District | Starts | Raw CUSUM | Days | BH-gated | Days | Weekly check | Days |", "|---|---|---|---|---|---|---|---|---|---|"]
    for e in d["events"]:
        lines.append(f"| {e['event']} | {e['group']} | {e['district']} | {e['onset']} | {e['cusum_alarm'] or 'none'} | {e['cusum_delay_days'] if e['cusum_delay_days'] is not None else '-'} | {e['bh_gated_alarm'] or 'none'} | {e['bh_gated_delay_days'] if e['bh_gated_delay_days'] is not None else '-'} | {e['weekly_alarm'] or 'none'} | {e['weekly_delay_days'] if e['weekly_delay_days'] is not None else '-'} |")
    lines += ["", f"Missed trend/district pairs: raw {d['raw_missed']}/{len(d['events'])}; BH-gated {d['gated_missed']}/{len(d['events'])}.", f"Held-out protection interval coverage: {f['dc_protection_period']['heldout_interval_coverage']:.1%} across {f['dc_protection_period']['samples']} rolling-origin windows. Each version uses calibration outcomes strictly before its own test month."]
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
    lines += ["", "fixed reorder point = a frozen May 4-31 mean setting the reorder point and fixed seven-day order quantity; checked only on supplier weekdays. It never adapts to later demand. Historical baselines are unconstrained. history xB = 28-day moving average x (lead + 7 days) x buffer B (the policy that produced the synthetic history uses 1.25). "
              "scoop_forecast = order-up-to on the LightGBM protection-period forecast. scoop_full = scoop_forecast plus the weekly CUSUM findings with the AI draft directions accepted. "
              "Directions and CUSUM reset on a model update. @ CR = newsvendor critical ratio per SKU; @ 92% = fixed service level. Compare policies at similar average pallets: the question is how much stock buys how much fill rate.", ""]
    followup=inv['weak_review_followup']
    lines += ["", f"Unmatched significant findings: {inv['unmatched_findings']}; total significant findings: {inv['total_exposed_significant_findings']}. Matched true-trend findings labeled persistent: {inv['true_trend_labeled_persistent']}/{inv['true_trend_matched_findings']}; matched temporary findings kept neutral: {inv['temporary_neutralized']}/{inv['temporary_matched_findings']}.",
              f"Weak candidates later confirmed by BH within 14 days: {followup['later_bh_confirmed']}/{followup['denominator']} complete followups; {followup['censored_candidates']} late-period candidates are censored. Random exploratory comparator: {followup['random_comparison_later_bh_confirmed']}/{followup['random_comparison_denominator']} (different scopes; no formal superiority claim).", "", "## Monthly forecast evidence", "",
              "| Version | Trained through | Calibration outcomes through | Daily WAPE | Daily coverage | Pinball p10 / p90 | Protection WAPE | Protection coverage |",
              "|---|---|---|---|---|---|---|---|"]
    for row in f['rolling_origin']:
        daily=row['store_sku_day']
        lines.append(f"| {row['version']} | {row['trained_through']} | {row['calibration_end']} | {daily['scoop_lightgbm']:.2%} | {daily['interval_coverage_p10_p90']:.2%} | {daily['pinball_p10']:.3f} / {daily['pinball_p90']:.3f} | {row['protection_wape']:.2%} | {row['protection_interval_coverage']:.2%} |")
    lines += ["", f"BH-gated missed strong targets: {d['strong_gated_missed']}/7; missed weak targets: {d['weak_gated_missed']}/4. Late gated detections (>14 days): {d['late_gated_detections']}.",
              f"Bounded weekly weak-review audit: {sum(len(v) for v in r.get('weak_reviews',{}).values())} checks across {len(r.get('weak_reviews',{}))} dates; maximum ten checks per date. Exploratory results never automatically change purchases.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    res = run()
    print(json.dumps({k: v for k, v in res.items() if k != "investigator"}, indent=1, default=str)[:4000])
