"""Deterministic timing layered over the unchanged daily stock-flow replay."""

from __future__ import annotations

import hashlib

from .config import (
    DEFAULT_SUPPLIER_WINDOW, DEMAND_HOURLY_WEIGHTS,
    DISPATCH_HOURLY_WEIGHTS, INTRADAY_STEP_MINUTES, SUPPLIER_WINDOWS,
)

MINUTES = tuple(range(0, 1441, INTRADAY_STEP_MINUTES))


def _cdf(weights: tuple[float, ...]) -> list[float]:
    values = [0.0]
    total = 0.0
    for weight in weights:
        for _ in range(60 // INTRADAY_STEP_MINUTES):
            total = min(1.0, total + weight / (60 // INTRADAY_STEP_MINUTES))
            values.append(total)
    values[-1] = 1.0
    return values


DEMAND_CDF = _cdf(DEMAND_HOURLY_WEIGHTS)
DISPATCH_CDF = _cdf(DISPATCH_HOURLY_WEIGHTS)


def arrival_minute(supplier: str, day: str) -> int:
    """One supplier/date instant, inclusive of each configured 10-minute window."""
    lo, hi = SUPPLIER_WINDOWS.get(supplier, DEFAULT_SUPPLIER_WINDOW)
    digest = hashlib.sha256(f'{supplier}|{day}'.encode()).digest()
    slot = int.from_bytes(digest[:8], 'big') % ((hi - lo) // INTRADAY_STEP_MINUTES + 1)
    return lo + slot * INTRADAY_STEP_MINUTES


def clock(day: str, minute: int) -> dict:
    hh, mm = divmod(minute, 60)
    stamp = f'{hh:02d}:{mm:02d}'
    return {'minute': minute, 'time': stamp, 'at': f'{day}T{stamp}:00'}


def first_shortage_minute(demand: float, opening: float, arrived: float, receipt: int) -> int | None:
    for minute, fraction in zip(MINUTES[:-1], DEMAND_CDF[:-1]):
        supply = opening + (arrived if minute >= receipt else 0.0)
        if demand * fraction > supply + 1e-9:
            return minute
    return None


def cumulative_loss(demand: float, opening: float, arrived: float,
                    receipt: int, final_loss: float) -> list[float]:
    """Monotone presentation loss, capped by the unchanged daily loss."""
    curve = []
    maximum = 0.0
    for minute, fraction in zip(MINUTES, DEMAND_CDF):
        landed = arrived if minute >= receipt else 0.0
        maximum = max(maximum, min(final_loss, max(0.0, demand * fraction - opening - landed)))
        curve.append(maximum)
    return curve


def enrich(result: dict, suppliers: list[str]) -> None:
    """Attach immutable profile and exact hourly increments to the result."""
    dates = result['dates']
    skus = result['skus']
    runs = result['runs']
    first = runs['scoop']['per_sku']
    opening = [first['pre_ship'][0][j] - first['arrived'][0][j] for j in range(len(skus))]
    arrivals = [[arrival_minute(supplier, day) for supplier in suppliers] for day in dates]
    result['intraday'] = {
        'step_minutes': INTRADAY_STEP_MINUTES, 'minutes': list(MINUTES),
        'demand_cdf': DEMAND_CDF, 'dispatch_cdf': DISPATCH_CDF,
        'arrival_minutes': arrivals, 'opening_on_hand': opening,
    }
    for run in runs.values():
        per = run['per_sku']
        hourly = {key: [] for key in ('on_hand', 'on_hand_delta', 'demand', 'shipped', 'lost', 'arrived')}
        prior = opening[:]
        for day, receipt_row in enumerate(arrivals):
            loss_curves = [cumulative_loss(
                per['demand'][day][j], prior[j], per['arrived'][day][j],
                receipt_row[j], per['lost'][day][j],
            ) for j in range(len(skus))]
            for hour in range(24):
                end = (hour + 1) * 60
                prev = hour * 60
                step = end // INTRADAY_STEP_MINUTES
                last = prev // INTRADAY_STEP_MINUTES
                row = {key: [] for key in hourly}
                for j in range(len(skus)):
                    dem = per['demand'][day][j]
                    ship = per['shipped'][day][j]
                    arrived = per['arrived'][day][j]
                    receipt = receipt_row[j]
                    arrived_hour = arrived if prev < receipt <= end else 0.0
                    shipped_hour = ship * (DISPATCH_CDF[step] - DISPATCH_CDF[last])
                    demand_hour = dem * (DEMAND_CDF[step] - DEMAND_CDF[last])
                    lost_hour = loss_curves[j][step] - loss_curves[j][last]
                    level = prior[j] + (arrived if end >= receipt else 0.0) - ship * DISPATCH_CDF[step]
                    previous_level = prior[j] + (arrived if prev >= receipt else 0.0) - ship * DISPATCH_CDF[last]
                    row['on_hand'].append(level)
                    row['on_hand_delta'].append(level - previous_level)
                    row['demand'].append(demand_hour)
                    row['shipped'].append(shipped_hour)
                    row['lost'].append(lost_hour)
                    row['arrived'].append(arrived_hour)
                for key, values in row.items():
                    hourly[key].append(values)
            prior = per['on_hand'][day][:]
        run['hourly'] = hourly
