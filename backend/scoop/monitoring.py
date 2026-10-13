"""Daily share monitoring: residuals, calibrated CUSUM charts and their cached results."""

from __future__ import annotations

import pickle
from dataclasses import dataclass

import pandas as pd

from .algorithms import cusum
from .algorithms.groups import Group, load_groups, membership
from .algorithms.runs import CALIB_END, CALIB_START, MONITOR_END, MONITOR_START, _cache_dir, artifacts
from .db import read_sql


@dataclass
class Monitoring:
    groups: list[Group]
    group_by_id: dict[str, Group]
    store_district: pd.Series
    calibration: cusum.Calibration
    series: pd.DataFrame  # Jun-Aug with z, s_up, s_down
    calib_resid: pd.DataFrame
    actual: pd.DataFrame  # store orders Apr-Aug
    expectations: pd.DataFrame


def _actual_units() -> pd.DataFrame:
    df = read_sql(
        "SELECT date, store_id, sku, ordered_units, shipped_units FROM store_orders WHERE date BETWEEN :a AND :b",
        a=CALIB_START.date(), b=MONITOR_END.date(),
    )
    df["date"] = pd.to_datetime(df.date)
    return df


def build() -> Monitoring:
    art = artifacts()
    groups = load_groups()
    skus = list(art.static.products.sku)
    mem = membership(groups, skus)
    store_district = art.static.stores.set_index("store_id").district
    path = _cache_dir() / "monitoring.pkl"
    actual = _actual_units()
    if path.exists():
        cal, series, calib_resid = pickle.loads(path.read_bytes())
    else:
        resid = cusum.residuals(actual, art.expectations, mem, store_district)
        calib_resid = resid[(resid.date >= CALIB_START) & (resid.date <= CALIB_END)]
        cal = cusum.calibrate(calib_resid)
        live = resid[(resid.date >= MONITOR_START) & (resid.date <= MONITOR_END)]
        series = cusum.monitor(live, cal)
        path.write_bytes(pickle.dumps((cal, series, calib_resid)))
    return Monitoring(groups, {g.id: g for g in groups}, store_district, cal, series, calib_resid, actual, art.expectations)


_M: Monitoring | None = None


def monitoring() -> Monitoring:
    global _M
    if _M is None:
        _M = build()
    return _M
