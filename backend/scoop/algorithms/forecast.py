"""Demand forecasting: one global LightGBM model over store x SKU x day.

* A Poisson objective gives the expected units (used for CUSUM expectations and sums).
* Quantile objectives at 0.1 / 0.9 give a daily interval.
* Features are calendar, weather, promotion, store and product attributes. There are no
  recent-sales lags on purpose: the model describes "normal patterns", so a new preference
  shift shows up as a residual for CUSUM instead of being absorbed by the forecast.
* One version retrains at each month boundary and stays frozen for procurement and detection.
* Protection-period intervals (lead time + review period) are bottom-up sums of the daily
  expectation, widened with empirical actual/forecast ratios measured in a backtest that used
  issued weather forecasts (not observed weather), so the interval includes forecast error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..db import read_sql

CATEGORICAL = ["store_id", "sku", "district", "format", "family"]
FORMATS = ("stick", "cup", "tub", "cone", "sandwich", "mochi", "multipack")
NUMERIC = [
    "size_factor", "dairy", "richness", "sweetness", "choc_coated", "low_sugar", "price_hkd", "sugar_100ml",
    "dow", "month", "doy_sin", "doy_cos", "holiday", "tmax", "rain_mm", "tmax_x_dairy",
    "tmax_x_dairy_water", "tmax_x_dairy_middle", "tmax_x_dairy_rich",
    *(f"tmax_x_format_{name}" for name in FORMATS), "promo_disc",
]
FEATURES = CATEGORICAL + NUMERIC

PARAMS = dict(learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.9, bagging_fraction=0.8,
              bagging_freq=1, verbose=-1, seed=7, num_threads=1)
ROUNDS = 350

HOLIDAYS = None  # loaded lazily from the generator so features match the synthetic calendar


def _holidays() -> set[date]:
    global HOLIDAYS
    if HOLIDAYS is None:
        from ..synth.generate import HOLIDAYS as H

        HOLIDAYS = set(H)
    return HOLIDAYS


# --------------------------------------------------------------------------- static frames


@dataclass
class Static:
    stores: pd.DataFrame
    products: pd.DataFrame
    promos: pd.DataFrame
    weather: pd.DataFrame
    forecasts: pd.DataFrame
    climatology: pd.Series

    @classmethod
    def load(cls) -> "Static":
        stores = read_sql("SELECT id AS store_id, district, size_factor FROM stores ORDER BY id")
        products = read_sql(
            """
            SELECT p.sku, p.format, p.price_hkd, p.cost_hkd, p.units_per_case, p.cases_per_pallet, p.moq_cases,
                   p.supplier_id, s.lead_time_days, s.order_weekday, s.review_days,
                   MAX(CASE WHEN pt.tag_id = 'dairy' THEN pt.value_num END) AS dairy,
                   MAX(CASE WHEN pt.tag_id = 'richness' THEN pt.value_num END) AS richness,
                   MAX(CASE WHEN pt.tag_id = 'sweetness' THEN pt.value_num END) AS sweetness,
                   MAX(CASE WHEN pt.tag_id = 'sugar_100ml' THEN pt.value_num END) AS sugar_100ml,
                   MAX(CASE WHEN pt.tag_id = 'feature:choc_coated' THEN 1 ELSE 0 END) AS choc_coated,
                   MAX(CASE WHEN pt.tag_id = 'health:low_sugar' THEN 1 ELSE 0 END) AS low_sugar,
                   MAX(CASE WHEN pt.tag_id LIKE 'family:%%' THEN split_part(pt.tag_id, ':', 2) END) AS family
            FROM products p JOIN suppliers s ON s.id = p.supplier_id JOIN product_tags pt ON pt.sku = p.sku
            GROUP BY p.sku, p.format, p.price_hkd, p.cost_hkd, p.units_per_case, p.cases_per_pallet, p.moq_cases,
                     p.supplier_id, s.lead_time_days, s.order_weekday, s.review_days
            ORDER BY p.sku
            """
        )
        promos = read_sql("SELECT sku, start_date, end_date, discount_pct FROM promotions")
        weather = read_sql("SELECT date, tmax, rain_mm FROM weather_daily ORDER BY date")
        weather["date"] = pd.to_datetime(weather.date)
        forecasts = read_sql("SELECT issued_date, target_date, tmax_fc, rain_fc FROM weather_forecasts")
        forecasts["issued_date"] = pd.to_datetime(forecasts.issued_date)
        forecasts["target_date"] = pd.to_datetime(forecasts.target_date)
        doy = weather.date.dt.dayofyear
        clim = weather.groupby(doy).tmax.mean().rolling(15, center=True, min_periods=1).mean()
        return cls(stores, products, promos, weather, forecasts, clim)

    def promo_frame(self, dates: pd.DatetimeIndex) -> pd.DataFrame:
        rows = []
        for r in self.promos.itertuples():
            for d in pd.date_range(r.start_date, r.end_date):
                if dates.min() <= d <= dates.max():
                    rows.append((d, r.sku, r.discount_pct))
        frame = pd.DataFrame(rows, columns=["date", "sku", "promo_disc"])
        return frame.groupby(["date", "sku"], as_index=False).promo_disc.max()


# --------------------------------------------------------------------------- features


def build_features(static: Static, dates: pd.DatetimeIndex, weather: pd.DataFrame | None = None) -> pd.DataFrame:
    """Store x SKU x date features; default weather is the previous issued forecast."""
    grid = pd.MultiIndex.from_product([dates, static.stores.store_id, static.products.sku], names=["date", "store_id", "sku"]).to_frame(index=False)
    grid = grid.merge(static.stores, on="store_id").merge(
        static.products[["sku", "format", "family", "dairy", "richness", "sweetness", "choc_coated", "low_sugar", "price_hkd", "sugar_100ml"]], on="sku"
    )
    w = issued_daily_weather(static, dates) if weather is None else weather
    grid = grid.merge(w[["date", "tmax", "rain_mm"]], on="date", how="left")
    grid = grid.merge(static.promo_frame(dates), on=["date", "sku"], how="left")
    grid["promo_disc"] = grid.promo_disc.fillna(0.0)
    grid["dow"] = grid.date.dt.weekday
    grid["month"] = grid.date.dt.month
    doy = grid.date.dt.dayofyear
    grid["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    grid["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    hol = _holidays()
    grid["holiday"] = grid.date.dt.date.isin(hol).astype(int)
    grid["tmax_x_dairy"] = grid.tmax * (0.45 - grid.dairy)
    # Piecewise weather responses can differ by dairy band and serving format.
    # The continuous interaction above remains available to the model.
    dairy_edges = np.quantile(static.products.dairy.to_numpy(), [1 / 3, 2 / 3])
    dairy_band = np.digitize(grid.dairy.to_numpy(), dairy_edges, right=True)
    grid["tmax_x_dairy_water"] = grid.tmax * (dairy_band == 0)
    grid["tmax_x_dairy_middle"] = grid.tmax * (dairy_band == 1)
    grid["tmax_x_dairy_rich"] = grid.tmax * (dairy_band == 2)
    for name in FORMATS:
        grid[f"tmax_x_format_{name}"] = grid.tmax * (grid["format"] == name)
    for c in NUMERIC:
        grid[c] = grid[c].astype(float)
    for c in CATEGORICAL:
        grid[c] = grid[c].astype("category")
    return grid


def forecast_weather(static: Static, issued: date, targets: pd.DatetimeIndex) -> pd.DataFrame:
    """Weather known on ``issued``: issued forecasts up to 16 days, climatology beyond."""
    fc = static.forecasts[static.forecasts.issued_date == pd.Timestamp(issued)].set_index("target_date")
    # Fit a seasonal fallback only to observations available at issue time.
    past = static.weather[static.weather.date <= pd.Timestamp(issued)]
    def seasonal(frame):
        phase = 2 * np.pi * frame.date.dt.dayofyear.to_numpy() / 365.25
        return np.column_stack([np.ones(len(frame)), np.sin(phase), np.cos(phase)])
    coef = np.linalg.lstsq(seasonal(past), past.tmax.to_numpy(), rcond=None)[0] if len(past) else np.array([25., 0., 0.])
    rain = float(past.rain_mm.mean()) if len(past) else 5.0
    rows = []
    for d in targets:
        if d in fc.index:
            rows.append((d, fc.loc[d, "tmax_fc"], fc.loc[d, "rain_fc"]))
        else:
            phase = 2 * np.pi * d.dayofyear / 365.25
            rows.append((d, float(np.array([1., np.sin(phase), np.cos(phase)]) @ coef), rain))
    return pd.DataFrame(rows, columns=["date", "tmax", "rain_mm"])


def training_frame(static: Static, start: date, end: date, orders: pd.DataFrame | None = None) -> pd.DataFrame:
    dates = pd.date_range(start, end)
    feats = build_features(static, dates, weather=issued_daily_weather(static, dates))
    y = (read_sql("SELECT date, store_id, sku, ordered_units FROM store_orders WHERE date BETWEEN :a AND :b", a=start,b=end)
         if orders is None else orders[pd.to_datetime(orders.date).between(pd.Timestamp(start),pd.Timestamp(end))][["date","store_id","sku","ordered_units"]].copy())
    y["date"] = pd.to_datetime(y.date)
    feats["store_id"] = feats.store_id.astype(str)
    feats["sku"] = feats.sku.astype(str)
    out = feats.merge(y, on=["date", "store_id", "sku"], how="inner")
    for c in CATEGORICAL:
        out[c] = out[c].astype("category")
    return out


# --------------------------------------------------------------------------- model


@dataclass
class DemandModel:
    trained_through: date
    models: dict[str, lgb.Booster] = field(default_factory=dict)
    categories: dict[str, list] = field(default_factory=dict)
    version: str = "legacy"

    @classmethod
    def train(cls, static: Static, start: date, end: date, rounds: int = ROUNDS,
              orders: pd.DataFrame | None = None, train_quantiles: bool = True) -> "DemandModel":
        frame = training_frame(static, start, end, orders=orders)
        cats = {c: list(frame[c].cat.categories) for c in CATEGORICAL}
        X, y = frame[FEATURES], frame.ordered_units.astype(float)
        m = cls(trained_through=end, categories=cats)
        m.models["mean"] = lgb.train({**PARAMS, "objective": "poisson"}, lgb.Dataset(X, y), rounds)
        for q in ((0.1, 0.9) if train_quantiles else ()):
            m.models[f"q{int(q * 100)}"] = lgb.train({**PARAMS, "objective": "quantile", "alpha": q}, lgb.Dataset(X, y), rounds // 2)
        return m

    def _align(self, feats: pd.DataFrame) -> pd.DataFrame:
        X = feats[FEATURES].copy()
        for c in CATEGORICAL:
            X[c] = pd.Categorical(X[c].astype(str), categories=self.categories[c])
        return X

    def predict(self, feats: pd.DataFrame, mean_only: bool = False) -> pd.DataFrame:
        X = self._align(feats)
        out = feats[["date", "store_id", "sku"]].copy()
        out["store_id"] = out.store_id.astype(str)
        out["sku"] = out.sku.astype(str)
        out["mean"] = self.models["mean"].predict(X, num_threads=1)
        if mean_only:
            return out
        out["p10"] = np.minimum(self.models["q10"].predict(X, num_threads=1), out["mean"])
        out["p90"] = np.maximum(self.models["q90"].predict(X, num_threads=1), out["mean"])
        return out


# --------------------------------------------------------------------------- protection period


def protection_days(products: pd.DataFrame) -> pd.Series:
    return (products.lead_time_days + products.review_days).set_axis(products.sku)


_PROTECTION_CACHE = {}


def protection_forecast(model: DemandModel, static: Static, issued: date, horizon: int | None = None,
                        order_calendar: bool = False, weather_scenario=None) -> pd.DataFrame:
    """Per SKU: expected DC demand over its protection period starting the day after ``issued``."""
    key = (id(model), id(static), issued, horizon, order_calendar, weather_scenario)
    if key in _PROTECTION_CACHE:
        fc, split = _PROTECTION_CACHE[key]
        return fc.copy(), split.copy()
    pdays = protection_days(static.products)
    if order_calendar:
        start = issued + timedelta(days=1)
        wait = ((static.products.order_weekday - start.weekday()) % 7).set_axis(static.products.sku)
        pdays = pdays + wait
    h = int(horizon or pdays.max())
    targets = pd.date_range(issued + timedelta(days=1), periods=h)
    pred = daily_mean(model, static, issued, targets, weather_scenario=weather_scenario)
    pred["day"] = (pred.date - pd.Timestamp(issued)).dt.days
    pred = pred.merge(pdays.rename("pdays"), left_on="sku", right_index=True)
    window = pred[pred.day <= pred.pdays]
    by_sku = window.groupby("sku").agg(mean=("mean", "sum"))
    by_sku_store = window.groupby(["sku", "store_id"])["mean"].sum().rename("mean").reset_index()
    by_sku["pdays"] = pdays
    result = (by_sku.reset_index(), by_sku_store)
    _PROTECTION_CACHE[key] = result
    return result[0].copy(), result[1].copy()


_DAILY_MEAN_CACHE = {}


def daily_mean(model, static, issued, targets, weather_scenario=None):
    key = (id(model), id(static), issued, weather_scenario)
    previous = _DAILY_MEAN_CACHE.get(key)
    if previous is not None and previous.date.min() <= targets.min() and previous.date.max() >= targets.max():
        return previous[previous.date.isin(targets)].copy()
    weather = forecast_weather(static, issued, targets)
    if weather_scenario is not None:
        start, end, temperature = weather_scenario
        weather.loc[weather.date.between(pd.Timestamp(start), pd.Timestamp(end)), 'tmax'] = temperature
    features = build_features(static, targets, weather=weather)
    predicted = model.predict(features, mean_only=True)
    if len(_DAILY_MEAN_CACHE) >= 14:
        del _DAILY_MEAN_CACHE[next(iter(_DAILY_MEAN_CACHE))]
    _DAILY_MEAN_CACHE[key] = predicted
    return predicted.copy()


def issued_daily_weather(static: Static, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Each day's features use the previous day's issued forecast, never realized weather."""
    fc = static.forecasts.copy()
    fc = fc[fc.issued_date == fc.target_date - pd.Timedelta(days=1)]
    out = pd.DataFrame({'date': dates}).merge(fc[['target_date', 'tmax_fc', 'rain_fc']], left_on='date', right_on='target_date', how='left')
    out = out.rename(columns={'tmax_fc': 'tmax', 'rain_fc': 'rain_mm'})
    for idx in out.index[out.tmax.isna()]:
        d = out.loc[idx, 'date']
        w = forecast_weather(static, (d - pd.Timedelta(days=1)).date(), pd.DatetimeIndex([d]))
        out.loc[idx, ['tmax', 'rain_mm']] = w[['tmax', 'rain_mm']].iloc[0].to_numpy()
    return out[['date', 'tmax', 'rain_mm']]


def calibrate_ratios(model: DemandModel, static: Static, issue_dates: list[date]) -> pd.DataFrame:
    """Backtest: actual / forecast protection-period demand per SKU and issue date."""
    rows = []
    actual = read_sql("SELECT date, sku, SUM(ordered_units) AS units FROM store_orders WHERE date BETWEEN :a AND :b GROUP BY date, sku",
                      a=min(issue_dates)+timedelta(days=1), b=max(issue_dates)+timedelta(days=int(protection_days(static.products).max())))
    actual["date"] = pd.to_datetime(actual.date)
    pdays = protection_days(static.products)
    for issued in issue_dates:
        if model.trained_through > issued:
            raise ValueError("Forecast calibration issue predates model training cutoff")
        fc, _ = protection_forecast(model, static, issued)
        for r in fc.itertuples():
            end = pd.Timestamp(issued) + pd.Timedelta(days=int(r.pdays))
            a = actual[(actual.sku == r.sku) & (actual.date > pd.Timestamp(issued)) & (actual.date <= end)].units.sum()
            rows.append({"issued": issued, "sku": r.sku, "forecast": r.mean, "actual": float(a), "pdays": int(pdays[r.sku])})
    out = pd.DataFrame(rows)
    out["ratio"] = out.actual / out.forecast.clip(lower=1.0)
    return out


@dataclass
class RatioQuantiles:
    """Empirical distribution of actual / forecast over the protection period."""

    values: np.ndarray

    def quantile(self, q: float) -> float:
        return float(np.quantile(self.values, q))

    def sigma(self) -> float:
        return (self.quantile(0.9) - self.quantile(0.1)) / 2.563
