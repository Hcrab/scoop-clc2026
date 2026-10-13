"""Monthly share monitoring with past-only calibration and explicit state resets."""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .algorithms import cusum
from .algorithms.groups import Group, load_groups, membership
from .algorithms.runs import (CALIB_END, CALIB_START, MONITOR_END, MONITOR_START,
                              _cache_dir, artifacts, month_start, month_end, version_for, CACHE)
from .db import read_sql, get_setting


@dataclass
class Monitoring:
    groups: list[Group]
    group_by_id: dict[str, Group]
    store_district: pd.Series
    calibration: cusum.Calibration  # compatibility: initial June calibration
    series: pd.DataFrame
    calib_resid: pd.DataFrame
    actual: pd.DataFrame
    expectations: pd.DataFrame
    calibrations: dict[str, cusum.Calibration] = field(default_factory=dict)
    calibration_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    review_log: dict[str,list] = field(default_factory=dict)

    def calibration_for(self, as_of: date | pd.Timestamp) -> cusum.Calibration:
        version = version_for(as_of)
        if self.calibrations and version not in self.calibrations:
            raise ValueError("No calibrated monitoring version for this month")
        return self.calibrations.get(version, self.calibration)

    def series_for(self, as_of: date | pd.Timestamp, through=None) -> pd.DataFrame:
        start = pd.Timestamp(month_start(as_of))
        end = pd.Timestamp(through if through is not None else as_of)
        return self.series[(self.series.date >= start) & (self.series.date <= end)].copy()


def _actual_units() -> pd.DataFrame:
    frame = read_sql("SELECT date, store_id, sku, ordered_units, shipped_units FROM store_orders WHERE date BETWEEN :a AND :b",
                     a=CALIB_START.date(), b=MONITOR_END.date())
    frame["date"] = pd.to_datetime(frame.date)
    return frame


def build() -> Monitoring:
    art = artifacts()
    groups = load_groups()
    mem = membership(groups, list(art.static.products.sku))
    store_district = art.static.stores.set_index("store_id").district
    actual = _actual_units()
    path = _cache_dir() / "monthly-monitoring-v1.pkl"
    if path.exists():
        calibrations, frames, series = pickle.loads(path.read_bytes())
    else:
        residual = cusum.residuals(actual, art.expectations, mem, store_district)
        calibrations, frames, rows = {}, {}, []
        for effective in pd.date_range(MONITOR_START, MONITOR_END, freq="MS"):
            run = art.run_for(effective.date())
            start, end = pd.Timestamp(run.metadata["calibration_start"]), pd.Timestamp(run.metadata["calibration_end"])
            frame = residual[residual.date.between(start,end)].copy()
            cal = cusum.calibrate(frame)
            live = residual[residual.date.between(effective,pd.Timestamp(month_end(effective.date())))].copy()
            # _run starts from zero on every new monthly forecast version.
            result = cusum.monitor(live,cal)
            result["model_version"] = run.model.version
            rows.append(result)
            calibrations[run.model.version], frames[run.model.version] = cal, frame
        series = pd.concat(rows,ignore_index=True)
        path.write_bytes(pickle.dumps((calibrations,frames,series)))
    june = version_for(MONITOR_START.date())
    return Monitoring(groups,{g.id:g for g in groups},store_district,calibrations[june],
                      series,frames[june],actual,art.expectations,calibrations,frames)


_M: Monitoring | None = None


def monitoring() -> Monitoring:
    global _M
    if _M is None:
        _M = build()
    return _M


def reset_cache() -> None:
    global _M
    _M = None


_LEGACY_CHART = None


def historical_chart(as_of: date, model_version: str | None = None):
    """Return the source curve/calibration for a saved plan, through yesterday.

    Plans saved before monthly lifecycle metadata belong to the original fixed
    baseline; never attach a newly retrained curve to their approved old finding.
    If that original artifact is unavailable, return an empty curve honestly.
    """
    global _LEGACY_CHART
    through = pd.Timestamp(as_of)-pd.Timedelta(days=1)
    if model_version is None or model_version.startswith('legacy'):
        path = CACHE / f"seed{get_setting('seed','42')}-issued-v3" / 'monitoring.pkl'
        if not path.exists():
            return None,pd.DataFrame()
        if _LEGACY_CHART is None:
            calibration,series,_=pickle.loads(path.read_bytes())
            _LEGACY_CHART=(calibration,series.assign(model_version='legacy-fixed-A-v3'))
        calibration,series=_LEGACY_CHART
        return calibration,series[series.date<=through].copy()
    current=monitoring()
    if model_version not in current.calibrations:
        return None,pd.DataFrame()
    selected=current.series[(current.series.model_version==model_version)&(current.series.date<=through)].copy()
    return current.calibrations[model_version],selected
