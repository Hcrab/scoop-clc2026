"""Immutable monthly forecast versions and past-only operational error calibration.

One monthly version is shared by procurement and detection. Calibration uses the
preceding month's genuinely forward predictions from its preceding version; no
live model is scored on training outcomes to estimate its own residual uncertainty.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import ROOT
from ..db import get_setting, session_scope
from ..models import ModelRun
from .forecast import (DemandModel, Static, build_features, calibrate_ratios,
                       issued_daily_weather, PARAMS, FEATURES, ROUNDS, protection_days)

CACHE = ROOT / "data" / "cache"
LOGIC_VERSION = "monthly-issued-v2"
TRAIN_START = date(2024, 6, 1)
RUN_A_END = date(2026, 3, 31)  # legacy aliases: April live version
RUN_B_END = date(2026, 5, 31)  # legacy alias: June live version
CALIB_START = pd.Timestamp("2026-04-01")
CALIB_END = pd.Timestamp("2026-05-31")
MONITOR_START = pd.Timestamp("2026-06-01")
MONITOR_END = pd.Timestamp("2026-08-31")


def month_start(as_of: date) -> date:
    return date(as_of.year, as_of.month, 1)


def month_end(as_of: date) -> date:
    return (pd.Timestamp(month_start(as_of)) + pd.offsets.MonthEnd(0)).date()


def version_for(as_of: date) -> str:
    return f"M{month_start(as_of):%Y%m}-v2-s{get_setting('seed', '42')}"


def model_metadata(as_of: date) -> dict:
    effective = month_start(as_of)
    cutoff = effective - timedelta(days=1)
    calibration_start = month_start(cutoff)
    return {"version": version_for(effective), "logic_version": LOGIC_VERSION,
            "effective_start": effective.isoformat(), "effective_end": month_end(effective).isoformat(),
            "training_start": TRAIN_START.isoformat(), "trained_through": cutoff.isoformat(),
            "calibration_start": calibration_start.isoformat(), "calibration_end": cutoff.isoformat(),
            "calibration_source_version": version_for(calibration_start),
            "calibration_method": "preceding_month_forward_errors_transferred_to_new_version",
            "weather_cutoff": "previous_day_issued_forecast", "seed": int(get_setting('seed', '42'))}


def _cache_dir() -> Path:
    d = CACHE / f"seed{get_setting('seed', '42')}-{LOGIC_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(model: DemandModel, name: str) -> None:
    d = _cache_dir()
    for k, booster in model.models.items():
        booster.save_model(str(d / f"{name}_{k}.txt"))
    meta = {**model_metadata(model.trained_through + timedelta(days=1)),
            "version":model.version, "model_keys":list(model.models),
            "artifact_kind":"null_world" if name.startswith("N") else "operational",
            "categories": model.categories, "params": PARAMS, "features": FEATURES, "rounds": ROUNDS}
    (d / f"{name}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _load(name: str) -> DemandModel | None:
    path = _cache_dir() / f"{name}_meta.json"
    if not path.exists():
        return None
    m = json.loads(path.read_text(encoding="utf-8"))
    if m.get("logic_version") != LOGIC_VERSION or m.get("features") != FEATURES or m.get("params") != PARAMS:
        return None
    model = DemandModel(trained_through=date.fromisoformat(m["trained_through"]),
                        categories=m["categories"], version=m["version"])
    for k in m.get("model_keys", ("mean", "q10", "q90")):
        model.models[k] = lgb.Booster(model_file=str(_cache_dir() / f"{name}_{k}.txt"))
    return model


_MODELS: dict[str, DemandModel] = {}


def monthly_model(as_of: date, static: Static) -> DemandModel:
    effective = month_start(as_of)
    name = version_for(effective)
    if name not in _MODELS:
        model = _load(name)
        if model is None:
            model = DemandModel.train(static, TRAIN_START, effective-timedelta(days=1))
            model.version = name
            _save(model, name)
        _MODELS[name] = model
        with session_scope() as session:
            if session.get(ModelRun, name) is None:
                session.add(ModelRun(id=name, trained_through=model.trained_through,
                    created_at=datetime.combine(effective, datetime.min.time()),
                    params={**model_metadata(effective), "lightgbm": PARAMS, "rounds": ROUNDS}, metrics={}))
    return _MODELS[name]


def get_model(name: str, static: Static) -> DemandModel:
    if name == "A":
        return monthly_model(date(2026,4,1), static)
    if name == "B":
        return monthly_model(date(2026,6,1), static)
    return monthly_model(date.fromisoformat(name), static)


@dataclass
class MonthlyRun:
    model: DemandModel
    metadata: dict
    ratios: pd.DataFrame
    ratio_values: np.ndarray


@dataclass
class Artifacts:
    static: Static
    model_a: DemandModel
    model_b: DemandModel
    expectations: pd.DataFrame
    bias_expectations: pd.DataFrame
    ratios: pd.DataFrame
    ratio_values: np.ndarray
    monthly_runs: dict[str, MonthlyRun] = field(default_factory=dict)

    def run_for(self, as_of: date) -> MonthlyRun:
        key = version_for(as_of)
        if key not in self.monthly_runs:
            self.monthly_runs[key] = build_monthly_run(as_of, self.static)
        return self.monthly_runs[key]


def build_monthly_run(as_of: date, static: Static) -> MonthlyRun:
    metadata = model_metadata(as_of)
    model = monthly_model(as_of, static)
    previous_start = date.fromisoformat(metadata["calibration_start"])
    previous_model = monthly_model(previous_start, static)
    max_days = int(protection_days(static.products).max())
    latest_issue = date.fromisoformat(metadata["calibration_end"])-timedelta(days=max_days)
    issue_dates = [d.date() for d in pd.date_range(previous_start, latest_issue, freq="7D")]
    path = _cache_dir() / f"{model.version}_ratios.pkl"
    if path.exists():
        ratios = pd.read_pickle(path)
    else:
        ratios = calibrate_ratios(previous_model, static, issue_dates)
        ratios["source_model_version"] = previous_model.version
        ratios["outcome_end"] = pd.to_datetime(ratios.issued) + pd.to_timedelta(ratios.pdays, unit="D")
        if ratios.outcome_end.max().date() > model.trained_through:
            raise ValueError("Calibration outcomes cross monthly cutoff")
        ratios.to_pickle(path)
    metadata["protection_calibration_issues"] = [x.isoformat() for x in issue_dates]
    metadata["protection_calibration_samples"] = len(ratios)
    metadata["protection_calibration_outcome_end"] = ratios.outcome_end.max().date().isoformat()
    calibration_path = _cache_dir() / f"{model.version}_calibration.json"
    if not calibration_path.exists():
        calibration_path.write_text(json.dumps({**metadata,
            "ratio_p10":float(np.quantile(ratios.ratio,.1)),
            "ratio_p50":float(np.quantile(ratios.ratio,.5)),
            "ratio_p90":float(np.quantile(ratios.ratio,.9))},indent=2),encoding="utf-8")
    return MonthlyRun(model, metadata, ratios, ratios.ratio.clip(0.3,3).to_numpy())


def build_artifacts() -> Artifacts:
    static = Static.load()
    path = _cache_dir() / "expectations-Apr-Aug.pkl"
    if path.exists():
        expectations = pd.read_pickle(path)
    else:
        rows = []
        for effective in pd.date_range(CALIB_START, MONITOR_END, freq="MS"):
            model = monthly_model(effective.date(), static)
            dates = pd.date_range(effective, month_end(effective.date()))
            pred = model.predict(build_features(static, dates, weather=issued_daily_weather(static, dates)))
            pred["model_version"] = model.version
            pred["run"] = "A" if effective <= CALIB_END else "B"  # old report/frontend compatibility
            rows.append(pred)
        expectations = pd.concat(rows, ignore_index=True)
        expectations.to_pickle(path)
    monthly = {version_for(d.date()):build_monthly_run(d.date(), static)
               for d in pd.date_range(MONITOR_START, MONITOR_END, freq="MS")}
    june = monthly[version_for(MONITOR_START.date())]
    return Artifacts(static, monthly_model(date(2026,4,1),static), june.model,
                     expectations, expectations[expectations.date.dt.month==5].copy(),
                     june.ratios, june.ratio_values, monthly)


_ARTIFACTS: Artifacts | None = None


def artifacts() -> Artifacts:
    global _ARTIFACTS
    if _ARTIFACTS is None:
        _ARTIFACTS = build_artifacts()
    return _ARTIFACTS


def reset_cache() -> None:
    global _ARTIFACTS
    _ARTIFACTS = None
    _MODELS.clear()
