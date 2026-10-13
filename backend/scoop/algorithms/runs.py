"""Train, cache and load the demand model runs used by the prototype.

Run A is trained through 31 Mar 2026 and scored on Apr-May 2026: that in-control period
calibrates the CUSUM thresholds and the protection-period intervals.
Run B is trained through 31 May 2026 and is the frozen purchasing model for Jun-Aug 2026.
Run A remains the detector baseline for Jun-Aug: calibration is genuinely out of sample.
These are prototype fixed-horizon runs, not a monthly retraining scheduler.
The planted events all start in June or later, so neither run has seen them.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import ROOT
from ..db import get_setting
from .forecast import CATEGORICAL, DemandModel, Static, build_features, calibrate_ratios, issued_daily_weather

CACHE = ROOT / "data" / "cache"
TRAIN_START = date(2024, 6, 1)
RUN_A_END = date(2026, 3, 31)
RUN_B_END = date(2026, 5, 31)
CALIB_START = pd.Timestamp("2026-04-01")
CALIB_END = pd.Timestamp("2026-05-31")
MONITOR_START = pd.Timestamp("2026-06-01")
MONITOR_END = pd.Timestamp("2026-08-31")


def _cache_dir() -> Path:
    seed = get_setting("seed", "42")
    d = CACHE / f"seed{seed}-issued-v3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(model: DemandModel, name: str) -> None:
    d = _cache_dir()
    for k, booster in model.models.items():
        booster.save_model(str(d / f"{name}_{k}.txt"))
    (d / f"{name}_meta.json").write_text(json.dumps({"trained_through": model.trained_through.isoformat(), "categories": model.categories}))


def _load(name: str) -> DemandModel | None:
    d = _cache_dir()
    meta = d / f"{name}_meta.json"
    if not meta.exists():
        return None
    m = json.loads(meta.read_text())
    model = DemandModel(trained_through=date.fromisoformat(m["trained_through"]), categories=m["categories"])
    for k in ("mean", "q10", "q90"):
        model.models[k] = lgb.Booster(model_file=str(d / f"{name}_{k}.txt"))
    return model


def get_model(name: str, static: Static) -> DemandModel:
    model = _load(name)
    if model is None:
        end = RUN_A_END if name == "A" else RUN_B_END
        model = DemandModel.train(static, TRAIN_START, end)
        _save(model, name)
    return model


@dataclass
class Artifacts:
    static: Static
    model_a: DemandModel
    model_b: DemandModel
    expectations: pd.DataFrame  # date, store_id, sku, mean, p10, p90 for Apr-Aug (A for Apr-May, B after)
    bias_expectations: pd.DataFrame  # model B on May 2026 (in-sample), for its share bias
    ratios: pd.DataFrame  # protection-period backtest
    ratio_values: np.ndarray


def build_artifacts() -> Artifacts:
    d = _cache_dir()
    static = Static.load()
    a = get_model("A", static)
    b = get_model("B", static)
    exp_path = d / "expectations.pkl"
    if exp_path.exists():
        expectations = pd.read_pickle(exp_path)
    else:
        e_a = a.predict(build_features(static, pd.date_range(CALIB_START, CALIB_END), weather=issued_daily_weather(static, pd.date_range(CALIB_START, CALIB_END))))
        e_b = a.predict(build_features(static, pd.date_range(MONITOR_START, MONITOR_END), weather=issued_daily_weather(static, pd.date_range(MONITOR_START, MONITOR_END))))
        expectations = pd.concat([e_a.assign(run="A"), e_b.assign(run="B")], ignore_index=True)
        expectations.to_pickle(exp_path)
    bias_path = d / "bias_expectations.pkl"
    if bias_path.exists():
        bias_exp = pd.read_pickle(bias_path)
    else:
        # model B scored on its last training month: its own bias, removed before CUSUM z-scores
        bias_exp = a.predict(build_features(static, pd.date_range("2026-05-01", RUN_B_END), weather=issued_daily_weather(static, pd.date_range("2026-05-01", RUN_B_END))))
        bias_exp.to_pickle(bias_path)
    ratio_path = d / "ratios-disjoint-v4.pkl"
    if ratio_path.exists():
        ratios = pd.read_pickle(ratio_path)
    else:
        mondays = [x.date() for x in pd.date_range("2026-04-06", "2026-04-20", freq="W-MON")]
        ratios = calibrate_ratios(a, static, mondays)
        ratios.to_pickle(ratio_path)
    values = ratios.ratio.clip(0.3, 3.0).to_numpy()
    return Artifacts(static, a, b, expectations, bias_exp, ratios, values)


_ARTIFACTS: Artifacts | None = None


def artifacts() -> Artifacts:
    global _ARTIFACTS
    if _ARTIFACTS is None:
        _ARTIFACTS = build_artifacts()
    return _ARTIFACTS


def reset_cache() -> None:
    global _ARTIFACTS
    _ARTIFACTS = None
