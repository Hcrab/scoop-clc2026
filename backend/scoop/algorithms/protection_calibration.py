"""Recent forward protection errors with a finite-rank quantile correction.

Weekly origins and pooled, serially dependent SKU outcomes do not give an exact
split-conformal coverage guarantee. Monthly mean models are reused unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..db import get_setting
from .forecast import Static, calibrate_ratios

METHOD = "recent_forward_split_conformal_v1"
WINDOW_DAYS = 56


@dataclass
class ProtectionCalibration:
    values: np.ndarray
    scores: pd.DataFrame
    metadata: dict

    def __post_init__(self):
        self.values = np.asarray(self.values, dtype=float)
        if self.values.ndim != 1 or not len(self.values) or not np.isfinite(self.values).all() or (self.values < 0).any():
            raise ValueError("Protection calibration requires finite nonnegative forward scores")

    def probability(self, q: float) -> float:
        """CDF probability of the supported finite rank, retaining the median."""
        if not 0 <= q <= 1:
            raise ValueError("Quantile probability must be in [0, 1]")
        if q == .5:
            return .5
        n = len(self.values)
        rank = np.floor((n + 1) * q) if q < .5 else np.ceil((n + 1) * q)
        return float(np.clip(rank, 1, n) / n)

    def quantile(self, q: float) -> float:
        if q == .5:
            return float(np.median(self.values))
        rank = int(round(self.probability(q) * len(self.values)))
        return float(np.sort(self.values)[rank - 1])


# Keep a separate cache; historical monthly ratio files remain the before baseline.
_RECENT_CACHE: dict[tuple, ProtectionCalibration] = {}


def reset_cache() -> None:
    _RECENT_CACHE.clear()


def recent_forward_calibration(static: Static, as_of: date) -> ProtectionCalibration:
    from .runs import monthly_model

    seed = str(get_setting("seed", "42"))
    key = (METHOD, seed, as_of, id(static))
    if key in _RECENT_CACHE:
        return _RECENT_CACHE[key]
    start = as_of - timedelta(days=WINDOW_DAYS)
    issues = [d.date() for d in pd.date_range(start, as_of - timedelta(days=1), freq="W-SUN")]
    by_month = {}
    for issued in issues:
        effective = (issued + timedelta(days=1)).replace(day=1)
        by_month.setdefault(effective, []).append(issued)
    frames = []
    for effective, origins in by_month.items():
        model = monthly_model(effective, static)
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
        "issue_start": start.isoformat(), "issue_cutoff": (as_of - timedelta(days=1)).isoformat(),
        "issue_dates": [d.isoformat() for d in issues],
        "scored_issue_start": min(scores.issued).isoformat(),
        "scored_issue_end": max(scores.issued).isoformat(),
        "actuals_cutoff": (as_of - timedelta(days=1)).isoformat(),
        "outcome_end": pd.Timestamp(scores.outcome_end.max()).date().isoformat(),
        "order_calendar": True, "ratio_clip": [0.3, 3.0],
        "coverage_note": "Finite-rank rolling forward calibration; serial dependence and pooling preclude exact coverage guarantees.",
    }
    calibrated = ProtectionCalibration(scores.ratio.clip(.3, 3.).to_numpy(), scores, metadata)
    # Bound memory while retaining repeated Play comparisons for recent as_of dates.
    if len(_RECENT_CACHE) >= 64:
        del _RECENT_CACHE[next(iter(_RECENT_CACHE))]
    _RECENT_CACHE[key] = calibrated
    return calibrated
