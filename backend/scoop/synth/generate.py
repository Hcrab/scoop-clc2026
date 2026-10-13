"""Generate the synthetic world: catalog, weather, store orders, DC inventory and planted events.

Demand per store x SKU x day is a Poisson-gamma draw around

    lambda = store size x SKU base x weekday x holiday x month
             x exp(a (T - 26))                  total weather response
             x exp(g_i (T - 26))                preference response (water-based up when hot)
             x exp(-r rain) x promotion x planted trend

The DC replenishes with a simple moving-average order-up-to policy (the "history" policy),
so stockouts and purchase orders look like a real operation that Scoop can improve on.
Everything is deterministic for a given seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .catalog import (
    BRAND_SUPPLIER,
    DISTRICT_CENTRES,
    DISTRICTS,
    FORMAT_BASE_DAILY,
    FORMAT_CASES_PER_PALLET,
    FORMAT_UNITS_PER_CASE,
    PRODUCTS,
    SUPPLIERS,
)

START = date(2024, 6, 1)
END = date(2026, 8, 31)
FORECAST_LEADS = 16
TEMP_REF = 26.0
WEATHER_TOTAL = 0.06  # demand x1.06 per degree above 26C
WEATHER_PREF = 0.045  # preference slope by (0.45 - dairy)
RAIN_EFFECT = 0.012
GAMMA_SHAPE = 6.0
REVIEW_DAYS = 7

# Approximate Hong Kong public holidays for the synthetic calendar.
HOLIDAYS = {
    date(2024, 7, 1), date(2024, 9, 18), date(2024, 10, 1), date(2024, 10, 11), date(2024, 12, 25),
    date(2024, 12, 26), date(2025, 1, 1), date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31),
    date(2025, 4, 4), date(2025, 4, 18), date(2025, 4, 19), date(2025, 4, 21), date(2025, 5, 1),
    date(2025, 5, 5), date(2025, 5, 31), date(2025, 7, 1), date(2025, 10, 1), date(2025, 10, 7),
    date(2025, 10, 29), date(2025, 12, 25), date(2025, 12, 26), date(2026, 1, 1), date(2026, 2, 17),
    date(2026, 2, 18), date(2026, 2, 19), date(2026, 4, 3), date(2026, 4, 4), date(2026, 4, 6),
    date(2026, 5, 1), date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 1),
}

DOW_FACTOR = np.array([0.90, 0.90, 0.92, 0.95, 1.08, 1.30, 1.25])
MONTH_FACTOR = np.array([0.95, 0.95, 0.98, 1.0, 1.0, 1.0, 1.10, 1.10, 1.0, 1.0, 0.97, 0.98])

HEATWAVE = {
    date(2026, 7, 14): 35.2,
    date(2026, 7, 15): 35.8,
    date(2026, 7, 16): 36.1,
    date(2026, 7, 17): 35.6,
    date(2026, 7, 18): 34.9,
}


@dataclass
class World:
    stores: pd.DataFrame
    suppliers: pd.DataFrame
    products: pd.DataFrame
    nutrition: pd.DataFrame
    tag_dimensions: pd.DataFrame
    tags: pd.DataFrame
    product_tags: pd.DataFrame
    weather: pd.DataFrame
    forecasts: pd.DataFrame
    promotions: pd.DataFrame
    store_orders: pd.DataFrame
    node_inventory: pd.DataFrame
    purchase_orders: pd.DataFrame
    nodes: pd.DataFrame
    events: pd.DataFrame


def _dates() -> list[date]:
    return [START + timedelta(days=i) for i in range((END - START).days + 1)]


def _ramp(days: np.ndarray, start: date, full: date, peak: float) -> np.ndarray:
    """Multiplier that is 1 before ``start``, rises linearly to ``1 + peak`` at ``full``, then holds."""
    s = (start - START).days
    f = (full - START).days
    progress = np.clip((days - s) / max(f - s, 1), 0.0, 1.0)
    return 1.0 + peak * progress


# --------------------------------------------------------------------------- catalog


def build_catalog(rng: np.random.Generator):
    stores = []
    n = 1
    for district, names in DISTRICTS.items():
        lat0, lon0 = DISTRICT_CENTRES[district]
        for j, name in enumerate(names):
            fmt, size = ("superstore", 1.6) if j == 0 else ("compact", 0.65) if j == 4 else ("standard", 1.0)
            stores.append(
                {
                    "id": f"S{n:02d}",
                    "name": name,
                    "district": district,
                    "format": fmt,
                    "lat": round(lat0 + rng.normal(0, 0.012), 5),
                    "lon": round(lon0 + rng.normal(0, 0.015), 5),
                    "size_factor": size,
                }
            )
            n += 1
    stores = pd.DataFrame(stores)

    suppliers = pd.DataFrame(
        [
            {"id": s, "name": nm, "lead_time_days": lt, "lead_time_sd": sd, "order_weekday": wd, "review_days": REVIEW_DAYS}
            for s, nm, lt, sd, wd in SUPPLIERS
        ]
    )

    products, nutrition, ptags = [], [], []
    for k, (name, brand, fmt, flavours, family, dairy, rich, sweet, features, health, size_ml, price) in enumerate(PRODUCTS, 1):
        sku = f"IC{k:03d}"
        cost = round(price * rng.uniform(0.52, 0.62), 2)
        upc = FORMAT_UNITS_PER_CASE[fmt]
        products.append(
            {
                "sku": sku,
                "name": name,
                "brand": brand,
                "format": fmt,
                "size_ml": size_ml,
                "units_per_case": upc,
                "cases_per_pallet": FORMAT_CASES_PER_PALLET[fmt],
                "price_hkd": price,
                "cost_hkd": cost,
                "supplier_id": BRAND_SUPPLIER[brand],
                "moq_cases": 2 if fmt in ("tub", "multipack", "mochi") else 3,
                "launch_date": date(2023, 1, 1),
                "status": "active",
                "description": f"{brand} {name.lower()}: {', '.join(f.replace('_', ' ') for f in flavours)} flavour {fmt}.",
            }
        )
        low_sugar = "low_sugar" in health
        serving = size_ml if fmt in ("stick", "cone", "cup", "sandwich") else (100 if fmt == "tub" else size_ml / (6 if "6" in name else 8 if "8" in name else 10 if "10" in name else 4))
        kcal100 = 70 + 170 * dairy * (0.5 + rich) + (45 if "choc_coated" in features else 0) - (25 if low_sugar else 0)
        sugar100 = 14 + 12 * sweet - (8 if low_sugar else 0)
        nutrition.append(
            {
                "sku": sku,
                "serving_ml": round(serving, 1),
                "kcal": round(kcal100 * serving / 100, 1),
                "sugar_g": round(sugar100 * serving / 100, 1),
                "fat_g": round((1 + 14 * dairy * rich + (6 if "choc_coated" in features else 0)) * serving / 100, 1),
                "protein_g": round((0.3 + 3.5 * dairy + (6 if "high_protein" in health else 0)) * serving / 100, 1),
            }
        )
        conf = lambda: round(float(rng.uniform(0.82, 0.98)), 2)  # noqa: E731
        ptags += [
            {"sku": sku, "tag_id": "dairy", "value_num": dairy, "source": "llm", "confidence": conf(), "rationale": "Ingredient list and description"},
            {"sku": sku, "tag_id": "richness", "value_num": rich, "source": "llm", "confidence": conf(), "rationale": "Description and fat content"},
            {"sku": sku, "tag_id": "sweetness", "value_num": sweet, "source": "llm", "confidence": conf(), "rationale": "Description and sugar content"},
            {"sku": sku, "tag_id": f"format:{fmt}", "value_num": 1.0, "source": "llm", "confidence": 0.99, "rationale": "Pack format"},
            {"sku": sku, "tag_id": f"family:{family}", "value_num": 1.0, "source": "llm", "confidence": conf(), "rationale": "Main flavour family"},
        ]
        ptags += [{"sku": sku, "tag_id": f"flavour:{f}", "value_num": 1.0, "source": "llm", "confidence": conf(), "rationale": "Named flavour"} for f in flavours]
        ptags += [{"sku": sku, "tag_id": f"feature:{f}", "value_num": 1.0, "source": "llm", "confidence": conf(), "rationale": "Product structure"} for f in features]
        ptags += [{"sku": sku, "tag_id": f"health:{h}", "value_num": 1.0, "source": "llm", "confidence": conf(), "rationale": "Pack claim"} for h in health]
        n_row = nutrition[-1]
        ptags += [
            {"sku": sku, "tag_id": "price_hkd", "value_num": price, "source": "computed", "confidence": 1.0, "rationale": None},
            {"sku": sku, "tag_id": "kcal_serving", "value_num": n_row["kcal"], "source": "computed", "confidence": 1.0, "rationale": None},
            {"sku": sku, "tag_id": "sugar_100ml", "value_num": round(sugar100, 1), "source": "computed", "confidence": 1.0, "rationale": None},
            {"sku": sku, "tag_id": "price_100ml", "value_num": round(price / size_ml * 100, 2), "source": "computed", "confidence": 1.0, "rationale": None},
        ]
    products = pd.DataFrame(products)
    nutrition = pd.DataFrame(nutrition)
    product_tags = pd.DataFrame(ptags)

    dims = [
        ("dairy", "Dairy content", "graded", None, "0 = pure water ice, 1 = full-cream ice cream", "llm"),
        ("richness", "Richness", "graded", None, "0 = light and refreshing, 1 = dense and indulgent", "llm"),
        ("sweetness", "Sweetness", "graded", None, "0 = barely sweet, 1 = very sweet", "llm"),
        ("format", "Format", "single", None, "Pack format", "llm"),
        ("family", "Flavour family", "single", None, "Main flavour family", "llm"),
        ("flavour", "Flavour", "multi", None, "Named flavours", "llm"),
        ("feature", "Structure", "multi", None, "Coating, crunch, filling, pieces", "llm"),
        ("health", "Health claim", "multi", None, "Claims printed on the pack", "llm"),
        ("price_hkd", "Unit price", "numeric", "HKD", "Shelf price per unit", "computed"),
        ("kcal_serving", "Energy per serving", "numeric", "kcal", "From nutrition label", "computed"),
        ("sugar_100ml", "Sugar per 100 ml", "numeric", "g", "sugar_g / serving_ml x 100", "computed"),
        ("price_100ml", "Price per 100 ml", "numeric", "HKD", "price / size_ml x 100", "computed"),
    ]
    tag_dimensions = pd.DataFrame(dims, columns=["id", "name", "kind", "unit", "definition", "source"])
    tag_rows = []
    for tag_id in sorted(set(product_tags.tag_id)):
        dim = tag_id.split(":")[0]
        name = tag_id.split(":")[1].replace("_", " ").title() if ":" in tag_id else tag_dimensions.set_index("id").loc[dim, "name"]
        tag_rows.append({"id": tag_id, "dimension_id": dim, "name": name, "definition": f"{dim}: {name}", "status": "active", "taxonomy_version": 1})
    tags = pd.DataFrame(tag_rows)
    return stores, suppliers, products, nutrition, tag_dimensions, tags, product_tags


# --------------------------------------------------------------------------- weather


def build_weather(rng: np.random.Generator, days: list[date]):
    n = len(days)
    doy = np.array([d.timetuple().tm_yday for d in days])
    clim = 24.0 + 6.0 * np.sin(2 * np.pi * (doy - 110) / 365.25)
    anomaly = np.zeros(n)
    for i in range(1, n):
        anomaly[i] = 0.7 * anomaly[i - 1] + rng.normal(0, 1.3)
    tmax = np.minimum(clim + anomaly, 33.8)
    for d, t in HEATWAVE.items():
        tmax[days.index(d)] = t
    wet_prob = 0.22 + 0.25 * (np.sin(2 * np.pi * (doy - 100) / 365.25) > 0)
    rain = np.where(rng.random(n) < wet_prob, rng.exponential(11.0, n), 0.0)
    weather = pd.DataFrame({"date": days, "tmax": np.round(tmax, 1), "rain_mm": np.round(rain, 1)})

    rows = []
    for i, issued in enumerate(days):
        for lead in range(1, FORECAST_LEADS + 1):
            j = i + lead
            if j >= n:
                break
            err_sd = 0.6 + 0.22 * lead
            weight = max(0.0, 1.0 - max(0, lead - 7) / 9.0)  # beyond a week the forecast drifts to climatology
            fc = weight * (tmax[j] + rng.normal(0, err_sd)) + (1 - weight) * clim[j]
            rain_fc = max(0.0, weight * rain[j] + (1 - weight) * 5.0 + rng.normal(0, 3 + lead))
            rows.append((issued, days[j], round(fc, 1), round(rain_fc, 1)))
    forecasts = pd.DataFrame(rows, columns=["issued_date", "target_date", "tmax_fc", "rain_fc"])
    return weather, forecasts, clim


# --------------------------------------------------------------------------- demand


def build_demand(rng, days, stores, products, product_tags, weather, *, planted=True):
    n_d, n_s, n_i = len(days), len(stores), len(products)
    day_idx = np.arange(n_d)
    tag_set = product_tags.groupby("sku")["tag_id"].apply(set).reindex(products.sku).tolist()
    dairy = product_tags[product_tags.tag_id == "dairy"].set_index("sku").value_num.reindex(products.sku).to_numpy()

    base = np.array([FORMAT_BASE_DAILY[f] for f in products.format]) * rng.lognormal(0, 0.35, n_i)
    size = stores.size_factor.to_numpy()
    dow = DOW_FACTOR[[d.weekday() for d in days]]
    hol = np.array([1.2 if d in HOLIDAYS else 1.0 for d in days])
    month = MONTH_FACTOR[[d.month - 1 for d in days]]
    temp = weather.tmax.to_numpy()
    rain = weather.rain_mm.to_numpy()

    total = dow * hol * month * np.exp(WEATHER_TOTAL * (temp - TEMP_REF)) * np.exp(-RAIN_EFFECT * rain)
    pref = np.exp(np.outer(temp - TEMP_REF, WEATHER_PREF * (0.45 - dairy)))  # d x i
    lam = total[:, None, None] * size[None, :, None] * base[None, None, :] * pref[:, None, :]

    # historical promotions (learned by the model) plus one unusually strong planted promotion
    promos = []
    promo_mult = np.ones((n_d, n_i))
    month_starts = [d for d in days if d.day == 1 and d < date(2026, 6, 1)]
    for ms in month_starts:
        for sku_i in rng.choice(n_i, size=3, replace=False):
            start = ms + timedelta(days=int(rng.integers(0, 20)))
            length = int(rng.integers(7, 11))
            disc = float(rng.choice([15, 20, 25]))
            s, e = (start - START).days, min((start - START).days + length - 1, n_d - 1)
            promo_mult[s : e + 1, sku_i] *= 1 + 1.2 * disc / 100
            promos.append((f"PR{len(promos) + 1:04d}", products.sku[sku_i], start, start + timedelta(days=length - 1), disc, "Monthly price promotion"))
    cone_idx = [i for i, t in enumerate(tag_set) if "format:cone" in t]
    p_start, p_end = date(2026, 7, 1), date(2026, 7, 7)
    s, e = (p_start - START).days, (p_end - START).days
    for i in cone_idx:
        promo_mult[s : e + 1, i] *= 1.85 if planted else 1 + 1.2 * 40 / 100
        promos.append((f"PR{len(promos) + 1:04d}", products.sku[i], p_start, p_end, 40.0, "Summer cone festival: buy one get one 50%"))
    lam *= promo_mult[:, None, :]

    # planted trends
    district = stores.district.to_numpy()
    fruit_water = np.array([("family:fruit" in t) and dairy[k] < 0.34 for k, t in enumerate(tag_set)])
    choc_coated = np.array(["feature:choc_coated" in t for t in tag_set])
    low_sugar = np.array(["health:low_sugar" in t for t in tag_set])
    trend = np.ones((n_d, n_s, n_i))
    fruit_schedule = {
        "Kowloon": (date(2026, 6, 22), date(2026, 7, 20), 0.40),
        "HK Island": (date(2026, 7, 6), date(2026, 8, 3), 0.35),
        "NT East": (date(2026, 7, 20), date(2026, 8, 17), 0.25),
    }
    for dist, (a, b, peak) in fruit_schedule.items():
        mult = _ramp(day_idx, a, b, peak)
        trend[:, district == dist, :] *= np.where(fruit_water[None, None, :], mult[:, None, None], 1.0)
    choc_mult = _ramp(day_idx, date(2026, 6, 8), date(2026, 7, 27), -0.25)
    trend *= np.where(choc_coated[None, None, :], choc_mult[:, None, None], 1.0)
    sugar_mult = _ramp(day_idx, date(2026, 6, 1), date(2026, 8, 31), 0.12)
    trend *= np.where(low_sugar[None, None, :], sugar_mult[:, None, None], 1.0)
    if planted:
        lam *= trend

    gamma = rng.gamma(GAMMA_SHAPE, 1 / GAMMA_SHAPE, size=lam.shape)
    orders = rng.poisson(lam * gamma).astype(np.int64)

    # planted bulk order: one store, one tub, two days
    bulk_store = int(np.where(stores.name.to_numpy() == "Tsuen Wan")[0][0])
    bulk_sku = int(np.where(products.name.to_numpy() == "Vanilla Bean Tub")[0][0])
    if planted:
        for d in (date(2026, 7, 9), date(2026, 7, 10)):
            orders[(d - START).days, bulk_store, bulk_sku] += 60

    promotions = pd.DataFrame(promos, columns=["id", "sku", "start_date", "end_date", "discount_pct", "note"])
    events = pd.DataFrame(
        [
            ("EV01", "trend", "family:fruit", None, ["Kowloon", "HK Island", "NT East"], date(2026, 6, 22), None, "persistent",
             "Fruit water-based ice rises in Kowloon from 22 Jun (+40% by 20 Jul), spreads to HK Island from 6 Jul and NT East from 20 Jul."),
            ("EV02", "trend", "feature:choc_coated", None, ["Kowloon", "HK Island", "NT East", "NT West"], date(2026, 6, 8), None, "persistent",
             "Chocolate-coated products decline network-wide from 8 Jun, -25% by 27 Jul."),
            ("EV03", "weak_trend", "health:low_sugar", None, ["Kowloon", "HK Island", "NT East", "NT West"], date(2026, 6, 1), None, "persistent",
             "Low-sugar products rise slowly from 1 Jun, +12% by 31 Aug."),
            ("EV04", "promo", "format:cone", None, ["Kowloon", "HK Island", "NT East", "NT West"], p_start, p_end, "one_off",
             "Cone festival promotion 1-7 Jul, uplift much stronger than usual promotions."),
            ("EV05", "bulk_order", None, products.sku[bulk_sku], ["NT West"], date(2026, 7, 9), date(2026, 7, 10), "data_issue",
             "Tsuen Wan orders 60 extra Vanilla Bean Tubs on 9 and 10 Jul (one-off party order)."),
            ("EV06", "heatwave", None, None, ["Kowloon", "HK Island", "NT East", "NT West"], date(2026, 7, 14), date(2026, 7, 18), "weather",
             "Record heat 34.9-36.1C on 14-18 Jul, above anything in the training history."),
        ],
        columns=["id", "kind", "tag_id", "sku", "districts", "start_date", "end_date", "expected_label", "note"],
    )
    return orders, promotions, events


# --------------------------------------------------------------------------- DC operations


def simulate_dc(rng, days, stores, products, suppliers, orders):
    """History policy: weekly order-up-to with a 28-day moving average and a fixed 25% buffer."""
    n_d, n_s, n_i = orders.shape
    sup = suppliers.set_index("id")
    lead = sup.loc[products.supplier_id, "lead_time_days"].to_numpy()
    lead_sd = sup.loc[products.supplier_id, "lead_time_sd"].to_numpy()
    weekday = sup.loc[products.supplier_id, "order_weekday"].to_numpy()
    upc = products.units_per_case.to_numpy()
    moq = products.moq_cases.to_numpy()

    total_orders = orders.sum(axis=1)  # d x i
    on_hand = (total_orders[:28].mean(axis=0) * 14).astype(np.int64)
    arrivals: dict[int, np.ndarray] = {}
    pipeline = np.zeros(n_i, dtype=np.int64)
    shipped = np.zeros_like(orders)
    inventory = np.zeros((n_d, n_i), dtype=np.int64)
    pos = []

    for d in range(n_d):
        if d in arrivals:
            on_hand += arrivals[d]
            pipeline -= arrivals[d]
        demand = total_orders[d]
        enough = on_hand >= demand
        ratio = np.where(enough, 1.0, np.divide(on_hand, np.maximum(demand, 1)))
        ship = np.floor(orders[d] * ratio[None, :]).astype(np.int64)
        ship = np.where(enough[None, :], orders[d], ship)
        shipped[d] = ship
        on_hand -= ship.sum(axis=0)
        inventory[d] = on_hand

        wd = days[d].weekday()
        due = np.where(weekday == wd)[0]
        if len(due):
            hist = total_orders[max(0, d - 27) : d + 1, due].mean(axis=0)
            target = hist * (lead[due] + REVIEW_DAYS) * 1.25
            position = on_hand[due] + pipeline[due]
            need = np.maximum(0, target - position)
            cases = np.ceil(need / upc[due]).astype(np.int64)
            cases = np.where(cases > 0, np.maximum(cases, moq[due]), 0)
            for k, i in enumerate(due):
                if cases[k] == 0:
                    continue
                lt = max(1, int(round(rng.normal(lead[i], lead_sd[i]))))
                units = int(cases[k] * upc[i])
                arrive = d + lt
                pipeline[i] += units
                if arrive < n_d:
                    arrivals.setdefault(arrive, np.zeros(n_i, dtype=np.int64))[i] += units
                pos.append(
                    {
                        "id": f"PO{len(pos) + 1:06d}",
                        "sku": products.sku[i],
                        "supplier_id": products.supplier_id[i],
                        "order_date": days[d],
                        "expected_date": days[d] + timedelta(days=int(lead[i])),
                        "received_date": days[arrive] if arrive < n_d else None,
                        "cases": int(cases[k]),
                        "source": "history",
                    }
                )
    return shipped, inventory, pd.DataFrame(pos)


# --------------------------------------------------------------------------- entry point


def null_orders(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproducible no-trend counterfactual for detector evaluation.

    Keeps the same catalog, weather (including heat), known promotions and RNG
    state entering demand generation. Removes preference drifts, exceptional
    promotion uplift and bulk orders. Poisson draws after changed intensities
    need not be paired with the planted world; this is not a causal estimator.
    """
    rng = np.random.default_rng(seed)
    days = _dates()
    stores, _, products, _, _, _, product_tags = build_catalog(rng)
    weather, _, _ = build_weather(rng, days)
    orders, _, _ = build_demand(rng, days, stores, products, product_tags, weather, planted=False)
    idx = pd.MultiIndex.from_product([days, stores.id, products.sku], names=["date", "store_id", "sku"])
    frame = pd.DataFrame({"ordered_units": orders.reshape(-1)}, index=idx).reset_index()
    return frame, weather


def generate(seed: int = 42) -> World:
    rng = np.random.default_rng(seed)
    days = _dates()
    stores, suppliers, products, nutrition, tag_dimensions, tags, product_tags = build_catalog(rng)
    weather, forecasts, _ = build_weather(rng, days)
    orders, promotions, events = build_demand(rng, days, stores, products, product_tags, weather)
    shipped, inventory, purchase_orders = simulate_dc(rng, days, stores, products, suppliers, orders)

    n_d, n_s, n_i = orders.shape
    idx = pd.MultiIndex.from_product([days, stores.id, products.sku], names=["date", "store_id", "sku"])
    store_orders = pd.DataFrame({"ordered_units": orders.reshape(-1), "shipped_units": shipped.reshape(-1)}, index=idx).reset_index()
    node_inventory = pd.DataFrame(
        {"on_hand_units": inventory.reshape(-1)},
        index=pd.MultiIndex.from_product([days, products.sku], names=["date", "sku"]),
    ).reset_index()

    # Cold-store capacity: tight in peak summer so that allocation under a capacity limit matters.
    pallets = inventory / (products.units_per_case.to_numpy() * products.cases_per_pallet.to_numpy())[None, :]
    summer = [i for i, d in enumerate(days) if d.month in (7, 8) and d.year == 2025]
    capacity = int(math.ceil(np.percentile(pallets[summer].sum(axis=1), 90) * 1.08))
    nodes = pd.DataFrame([{"id": "DC1", "name": "Tsing Yi Cold Store", "kind": "dc_cold_store", "capacity_pallets": capacity}])

    return World(stores, suppliers, products, nutrition, tag_dimensions, tags, product_tags, weather, forecasts,
                 promotions, store_orders, node_inventory, purchase_orders, nodes, events)
