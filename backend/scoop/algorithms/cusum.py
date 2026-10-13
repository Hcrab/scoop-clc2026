"""Weather-adjusted CUSUM on attribute shares.

For every monitored group g (a tag or a band) and district c, each day:

    actual share    a = units(g, c) / units(all, c)
    expected share  e = sum of model expectations for g / for all  (observed weather, promotions)
    z               = (a - e) / sd_gc          sd from an in-control calibration period
    S_up            = max(0, S_up + z - k)
    S_down          = max(0, S_down - z - k)

The model already explains weather, season, weekday and promotions, so z only carries what
those cannot explain. The threshold h is set by block-bootstrapping in-control z series toward an empirical ``ARL0`` target. BH gates approximate bootstrap p-values; dependence
and repeated daily testing mean there is no exact FDR or ARL guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

K = 0.25  # reference value: tuned for small, slow shifts (half of a 0.5 sd shift)
ARL0 = 90
FDR_Q = 0.10
BLOCK = 7


def shares(units: pd.DataFrame, membership: pd.DataFrame, store_district: pd.Series, value: str) -> pd.DataFrame:
    """Daily share of each group per district. ``units`` has date, store_id, sku and a value column."""
    u = units.assign(district=units.store_id.map(store_district))
    by = u.groupby(["date", "district", "sku"])[value].sum().unstack("sku", fill_value=0.0)
    by = by.reindex(columns=membership.index, fill_value=0.0)
    total = by.sum(axis=1)
    group_units = by.to_numpy() @ membership.to_numpy()
    out = pd.DataFrame(group_units, index=by.index, columns=membership.columns).div(total, axis=0)
    out = out.stack().rename("share").reset_index().rename(columns={"level_2": "group"})
    out.columns = ["date", "district", "group", "share"]
    return out


def residuals(actual_units: pd.DataFrame, expected_units: pd.DataFrame, membership: pd.DataFrame, store_district: pd.Series) -> pd.DataFrame:
    a = shares(actual_units, membership, store_district, "ordered_units").rename(columns={"share": "actual_share"})
    e = shares(expected_units, membership, store_district, "mean").rename(columns={"share": "expected_share"})
    r = a.merge(e, on=["date", "district", "group"])
    r["resid"] = r.actual_share - r.expected_share
    return r


@dataclass
class Calibration:
    sd: pd.Series  # index (group, district)
    bias: pd.Series  # mean in-control residual per series (model bias), removed before z
    h: float
    null_stats: np.ndarray  # stationary in-control CUSUM values for p-values

    def p_value(self, s: float) -> float:
        return float((np.sum(self.null_stats >= s) + 1) / (len(self.null_stats) + 1))


def _run(z: np.ndarray, k: float = K) -> tuple[np.ndarray, np.ndarray]:
    up, down = np.zeros_like(z), np.zeros_like(z)
    su = sd = 0.0
    for t, v in enumerate(z):
        su = max(0.0, su + v - k)
        sd = max(0.0, sd - v - k)
        up[t], down[t] = su, sd
    return up, down


def _bootstrap_paths(zs: list[np.ndarray], n_paths: int, length: int, rng: np.random.Generator) -> np.ndarray:
    paths = np.empty((n_paths, length))
    for p in range(n_paths):
        z = zs[rng.integers(len(zs))]
        pieces = []
        while sum(len(x) for x in pieces) < length:
            block = min(BLOCK, len(z))
            start = rng.integers(0, len(z) - block + 1)
            pieces.append(z[start : start + block])
        paths[p] = np.concatenate(pieces)[:length]
    return paths


def calibrate(calib: pd.DataFrame, seed: int = 11) -> Calibration:
    """``calib`` is the residual frame for an in-control period (no planted events)."""
    sd = calib.groupby(["group", "district"]).resid.std().clip(lower=1e-4)
    bias = calib.groupby(["group", "district"]).resid.mean()
    zs = []
    for key, part in calib.groupby(["group", "district"]):
        zs.append((part.sort_values("date").resid.to_numpy() - part.resid.mean()) / sd[key])
    rng = np.random.default_rng(seed)
    paths = _bootstrap_paths(zs, 800, 400, rng)

    up_paths = np.array([_run(z)[0] for z in paths])
    def arl(h: float) -> float:
        hit = up_paths >= h
        return float(np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, up_paths.shape[1] + 1).mean())

    lo, hi = 1.0, 12.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if arl(mid) < ARL0:
            lo = mid
        else:
            hi = mid
    h = round(hi, 2)
    stationary = up_paths[:500, 60:].ravel()
    return Calibration(sd=sd, bias=bias, h=h, null_stats=stationary)


def monitor(resid: pd.DataFrame, cal: Calibration) -> pd.DataFrame:
    """Add z, S_up and S_down to a residual frame (sorted per series)."""
    out = []
    for (g, c), part in resid.groupby(["group", "district"]):
        part = part.sort_values("date").copy()
        sd = cal.sd.get((g, c), 1e-3)
        part["z"] = (part.resid - cal.bias.get((g, c), 0.0)) / sd
        part["s_up"], part["s_down"] = _run(part.z.to_numpy())
        out.append(part)
    return pd.concat(out, ignore_index=True)


def benjamini_hochberg(p: np.ndarray, q: float = FDR_Q) -> tuple[np.ndarray, np.ndarray]:
    """Return (reject mask, adjusted q-values)."""
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    qvals = np.empty(n)
    qvals[order] = np.minimum(adj, 1.0)
    return qvals <= q, qvals


def alarms_as_of(series: pd.DataFrame, cal: Calibration, as_of: pd.Timestamp, lookback_days: int = 7) -> pd.DataFrame:
    """Charts that are high on ``as_of``, with first crossing date, p-values and BH decisions."""
    hist = series[series.date <= as_of]
    rows = []
    for (g, c), part in hist.groupby(["group", "district"]):
        part = part.sort_values("date")
        last = part.iloc[-1]
        for direction, col in (("up", "s_up"), ("down", "s_down")):
            s = float(last[col])
            crossed = part[part[col] >= cal.h]
            # start of the current run: last day the statistic was zero before now
            zero = part[part[col] == 0]
            run_start = zero.date.max() if len(zero) else part.date.min()
            first_cross = crossed[crossed.date >= run_start].date.min() if len(crossed) else pd.NaT
            rows.append({
                "group": g, "district": c, "direction": direction, "statistic": s,
                "first_cross": first_cross, "run_start": run_start,
                "p_value": cal.p_value(s),
            })
    out = pd.DataFrame(rows)
    if out.empty:
        cols = ["group", "district", "direction", "statistic", "first_cross", "run_start", "p_value", "q_value", "significant", "near_miss"]
        return pd.DataFrame(columns=cols).astype({"significant": bool, "near_miss": bool})
    reject, qv = benjamini_hochberg(out.p_value.to_numpy())
    out["q_value"] = qv
    out["significant"] = (out.statistic >= cal.h) & reject
    out["near_miss"] = ~out.significant & (out.statistic >= 0.5 * cal.h)
    return out


def weekly_baseline_alarms(series: pd.DataFrame, cal_resid: pd.DataFrame, cal: Calibration, seed: int = 5) -> tuple[pd.DataFrame, float]:
    """Comparison detector: weekly mean z above a threshold with the same false-alarm rate."""
    rng = np.random.default_rng(seed)
    zs = []
    for key, part in cal_resid.groupby(["group", "district"]):
        zs.append((part.sort_values("date").resid.to_numpy() - part.resid.mean()) / cal.sd[key])
    paths = _bootstrap_paths(zs, 3000, 7, rng)
    weekly = paths.mean(axis=1)
    # weekly checks with the same ARL0 in days: P(alarm per week) = 7 / ARL0
    thr = float(np.quantile(weekly, 1 - 7 / ARL0))
    s = series.copy()
    s["week"] = s.date - pd.to_timedelta(s.date.dt.weekday, unit="D")
    wk = s.groupby(["group", "district", "week"]).z.mean().rename("weekly_z").reset_index()
    wk["alarm_date"] = wk.week + pd.Timedelta(days=6)
    wk["up"] = wk.weekly_z > thr
    wk["down"] = wk.weekly_z < -thr
    return wk, thr
