"""One-sided upper calibration for the quantile actually used by procurement.

Base demand intervals stay unchanged. Forward excesses above the then-operational
upper target widen that target only; no central-interval adjustment can shrink it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..db import get_setting
from .forecast import Static, calibrate_ratios

METHOD = "one_sided_forward_upper_conformal_v2"
WINDOW_DAYS = 56


@dataclass
class ProtectionCalibration:
    values: np.ndarray
    scores: pd.DataFrame
    metadata: dict
    source_distributions: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self):
        self.values = np.asarray(self.values, dtype=float)
        if self.values.ndim != 1 or not len(self.values) or not np.isfinite(self.values).all() or (self.values < 0).any():
            raise ValueError("Protection calibration requires finite nonnegative forward scores")

    def probability(self, q: float) -> float:
        """Upper-tail finite-sample rank; never a symmetric-tail correction."""
        if not 0 <= q <= 1:
            raise ValueError("Quantile probability must be in [0, 1]")
        n = len(self.scores)
        if not n:
            raise ValueError("No forward upper-tail calibration outcomes")
        rank = np.ceil((n + 1) * q)
        return float(np.clip(rank, 1, n) / n)

    def quantile(self, q: float) -> float:
        """Unchanged base ratio percentile for p10/p50/p90 and quadrature."""
        return float(np.quantile(self.values, q))

    def upper_correction(self, q: float) -> float:
        """Positive normalized forward excess above the same requested quantile."""
        n = len(self.scores)
        rank = int(round(self.probability(q) * n))
        base = self.scores.source_model_version.map({
            version: float(np.quantile(values, q))
            for version, values in self.source_distributions.items()})
        if base.isna().any():
            raise ValueError("Missing then-operational upper-quantile distribution")
        forecast = self.scores.forecast.to_numpy(dtype=float)
        excess = np.maximum(0., (self.scores.actual.to_numpy(dtype=float)
                          - forecast * base.to_numpy()) / np.maximum(forecast, 1.))
        return float(np.partition(excess, rank - 1)[rank - 1])

    def upper_target(self, mean: float, base_upper_ratio: float, q: float) -> float:
        return float(mean * base_upper_ratio + max(mean, 1.) * self.upper_correction(q))

    def upper_quantile(self, q: float) -> float:
        return self.quantile(q) + self.upper_correction(q)


# Keep a separate cache; historical monthly ratio files remain the before baseline.
_RECENT_CACHE: dict[tuple, ProtectionCalibration] = {}


def reset_cache() -> None:
    _RECENT_CACHE.clear()


def recent_forward_calibration(static: Static, as_of: date) -> ProtectionCalibration:
    from .runs import build_monthly_run

    seed = str(get_setting("seed", "42"))
    key = (METHOD, seed, as_of, id(static))
    if key in _RECENT_CACHE:
        return _RECENT_CACHE[key]
    start = as_of - timedelta(days=WINDOW_DAYS)
    # The lookback is in planning origins; each forecast was issued the day before.
    origins = [d.date() for d in pd.date_range(start, as_of - timedelta(days=1), freq="W-MON")]
    issues = [origin - timedelta(days=1) for origin in origins]
    by_month = {}
    for issued in issues:
        effective = (issued + timedelta(days=1)).replace(day=1)
        by_month.setdefault(effective, []).append(issued)
    frames, distributions = [], {}
    for effective, origins in by_month.items():
        monthly = build_monthly_run(effective, static)
        model = monthly.model
        distributions[model.version] = monthly.ratio_values
        scores = calibrate_ratios(model, static, origins, order_calendar=True, as_of=as_of)
        scores["source_model_version"] = model.version
        scores["trained_through"] = model.trained_through
        frames.append(scores)
    scores = pd.concat(frames, ignore_index=True)
    if scores.empty:
        raise ValueError("No fully observed recent forward protection outcomes available")
    metadata = {
        "method": METHOD, "seed": seed, "as_of": as_of.isoformat(),
        "window_days": WINDOW_DAYS, "sample_count": len(scores),
        "planning_start": start.isoformat(),
        "issue_start": min(issues).isoformat(), "issue_cutoff": (as_of - timedelta(days=1)).isoformat(),
        "issue_dates": [d.isoformat() for d in issues],
        "scored_issue_start": min(scores.issued).isoformat(),
        "scored_issue_end": max(scores.issued).isoformat(),
        "actuals_cutoff": (as_of - timedelta(days=1)).isoformat(),
        "outcome_end": pd.Timestamp(scores.outcome_end.max()).date().isoformat(),
        "order_calendar": True, "ratio_clip": [0.3, 3.0],
        "planning_origins": [d.date().isoformat() for d in pd.date_range(start, as_of - timedelta(days=1), freq="W-MON")],
        "calibrates": "Only the ordering upper target, at its actual critical ratio/service target",
        "score": "max(0, (actual - then_operational_upper_target) / max(forecast, 1))",
        "coverage_note": "Finite-rank rolling forward calibration; serial dependence and pooling preclude exact coverage guarantees.",
    }
    current = build_monthly_run(as_of, static)
    calibrated = ProtectionCalibration(current.ratio_values, scores, metadata, distributions)
    # Bound memory while retaining repeated Play comparisons for recent as_of dates.
    if len(_RECENT_CACHE) >= 64:
        del _RECENT_CACHE[next(iter(_RECENT_CACHE))]
    _RECENT_CACHE[key] = calibrated
    return calibrated
