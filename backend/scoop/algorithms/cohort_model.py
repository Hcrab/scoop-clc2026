"""Read-only conditional cohort tree and two-level empirical Bayes demand effects."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
from math import exp, log, sqrt

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..models import Product, Promotion, Store, StoreOrder

PERMUTATIONS = 199
SEED = 20261014
Z80 = 1.2816


def project_level(series, window):
    """Keep the no-extrapolation projection boundary for a later trend model."""
    return [float(series[-1])] * int(window) if len(series) else []


def _dl(y, v):
    """DerSimonian-Laird variance; a singleton has no estimable heterogeneity."""
    if len(y) < 2:
        return None
    w = 1 / v
    mean = np.dot(w, y) / w.sum()
    q = np.dot(w, (y - mean) ** 2)
    c = w.sum() - np.dot(w, w) / w.sum()
    return float(max(0., (q - (len(y) - 1)) / c)) if c > 0 else 0.


def _gain(y, v, mask):
    w = 1 / v
    total = np.dot(w, y) ** 2 / w.sum()
    return float(np.dot(w[mask], y[mask]) ** 2 / w[mask].sum()
                 + np.dot(w[~mask], y[~mask]) ** 2 / w[~mask].sum() - total)


def fit_units(units, groups):
    """Fit independent SKU/district observations; inputs are never mutated.

    Unit fields: sku, district, y, v, expected_recent (or E_r), plus optional trace.
    Groups may be Group objects, id->Group mapping, or id->SKU iterable mapping.
    """
    rows = [dict(u) for u in units]
    if isinstance(groups, dict):
        catalog = {key: set(getattr(value, 'skus', value)) for key, value in groups.items()}
    else:
        catalog = {g.id: set(g.skus) for g in groups}
    rows.sort(key=lambda u: (u['sku'], u['district']))
    for u in rows:
        if not np.isfinite(u['y']) or not np.isfinite(u['v']) or u['v'] <= 0:
            raise ValueError('Each unit needs finite y and positive v')
    n = len(rows)
    if not n:
        return {'leaves': [], 'sku_factors': {}, 'units': [], 'method': {'status': 'no_eligible_units'}}
    y = np.array([u['y'] for u in rows], float)
    v = np.array([u['v'] for u in rows], float)
    sku = np.array([u['sku'] for u in rows])
    district = np.array([u['district'] for u in rows])
    features = {g: np.array([s in members for s in sku], bool) for g, members in sorted(catalog.items())}
    features.update({f'district:{d}': district == d for d in sorted(set(district))})
    rng = np.random.default_rng(SEED)
    leaves = []
    tested = []

    def grow(indices, path, p_path, depth):
        choices = []
        for key, values in features.items():
            mask = values[indices]
            if mask.all() or not mask.any():
                continue
            if len(set(sku[indices[mask]])) < 3 or len(set(sku[indices[~mask]])) < 3:
                continue
            choices.append((key, mask))
        if depth < 3 and choices:
            gains = [ _gain(y[indices], v[indices], mask) for _, mask in choices]
            winner = int(np.argmax(gains))
            observed = gains[winner]
            maximum = []
            for _ in range(PERMUTATIONS):
                order = rng.permutation(len(indices))
                py, pv = y[indices][order], v[indices][order]
                maximum.append(max(_gain(py, pv, mask) for _, mask in choices))
            p = float(np.mean(np.array(maximum) >= observed))
            tested.append({'path': path, 'candidate_count': len(choices), 'gain': observed,
                           'p_value': p, 'permutations': PERMUTATIONS})
            if p < .05:
                key, mask = choices[winner]
                grow(indices[mask], path + [{'id': key, 'included': True}], p_path + [p], depth + 1)
                grow(indices[~mask], path + [{'id': key, 'included': False}], p_path + [p], depth + 1)
                return
        leaves.append({'tag_path': path, 'split_p_values': p_path,
                       '_indices': indices, 'districts': sorted(set(district[indices])),
                       'skus': sorted(set(sku[indices]))})

    grow(np.arange(n), [], [], 0)
    estimates = []
    variances = []
    for leaf in leaves:
        ix = leaf['_indices']
        w = 1 / v[ix]
        estimates.append(float(np.dot(w, y[ix]) / w.sum()))
        variances.append(float(1 / w.sum()))
    tau_b = _dl(np.array(estimates), np.array(variances)) or 0.
    for leaf, raw, V in zip(leaves, estimates, variances):
        b = tau_b / (tau_b + V) if tau_b > 0 else 0.
        mu = raw * b
        var_mu = V * b
        ix = leaf.pop('_indices')
        tau_l_raw = _dl(y[ix], v[ix])
        tau_l = tau_b if tau_l_raw is None else tau_l_raw
        leaf.update(id='C' + sha256('|'.join(f"{r['id']}={int(r['included'])}" for r in leaf['tag_path']).encode()).hexdigest()[:12],
                    raw_estimate=raw, variance=V, posterior_mean=mu,
                    posterior_variance=var_mu,
                    interval_80=[mu - Z80 * sqrt(var_mu), mu + Z80 * sqrt(var_mu)],
                    shrinkage={'between_leaf_variance': tau_b, 'data_weight': b, 'toward_zero_weight': 1 - b,
                               'within_leaf_variance': tau_l, 'within_fallback': tau_l_raw is None})
        for j in ix:
            if tau_l == 0:
                m, conditional, leaf_weight = mu, 0., 1.
            else:
                conditional = 1 / (1 / v[j] + 1 / tau_l)
                leaf_weight = conditional / tau_l
                m = conditional * (y[j] / v[j] + mu / tau_l)
            rows[j].update(m=float(m), s2=float(conditional + var_mu),
                           conditional_variance=float(conditional),
                           leaf_weight=float(leaf_weight), leaf_id=leaf['id'])
    by_sku = defaultdict(list)
    for u in rows:
        by_sku[u['sku']].append(u)
    factors = {}
    for name, parts in sorted(by_sku.items()):
        demand = np.array([float(u.get('expected_recent', u.get('E_r', 0))) for u in parts])
        weights = demand / demand.sum() if demand.sum() > 0 else np.full(len(parts), 1 / len(parts))
        mean = float(sum(w * u['m'] for w, u in zip(weights, parts)))
        variance = float(sum((w ** 2) * u['conditional_variance'] for w, u in zip(weights, parts)))
        for leaf_id in {u['leaf_id'] for u in parts}:
            shared = [i for i, u in enumerate(parts) if u['leaf_id'] == leaf_id]
            leaf_var = next(l['posterior_variance'] for l in leaves if l['id'] == leaf_id)
            variance += leaf_var * float(sum(weights[i] for i in shared)) ** 2
        sd = sqrt(variance)
        factors[name] = {'f10': exp(mean - Z80 * sd), 'f50': exp(mean),
                         'f90': exp(mean + Z80 * sd), 'm': mean, 's2': variance}
    return {'leaves': leaves, 'sku_factors': factors, 'units': rows,
            'method': {'tree': 'inverse-variance conditional inference; max depth 3; min 3 distinct SKUs per child',
                       'permutations': PERMUTATIONS, 'seed': SEED, 'split_alpha': .05,
                       'tested_nodes': tested, 'eb': 'two-level DerSimonian-Laird',
                       'sku_covariance': 'district demand weights; conditional variances independent; shared leaf posterior covariance',
                       'projection': 'level, no extrapolation'}}


def fit(plan, session=None):
    """Prepare observations from recorded orders and issued monthly expectations."""
    if session is None:
        from ..db import SessionLocal
        with SessionLocal() as own:
            return fit(plan, own)
    from ..ai.exploration_tools import _expectations, _groups

    end = plan.week_start - timedelta(days=1)
    recent_start = end - timedelta(days=13)
    start = recent_start - timedelta(days=56)
    stores = {s.id: s.district for s in session.scalars(select(Store))}
    skus = sorted(session.scalars(select(Product.sku)))
    orders = session.execute(select(StoreOrder.date, StoreOrder.store_id, StoreOrder.sku, StoreOrder.ordered_units)
                             .where(StoreOrder.date.between(start, end))).all()
    promotions = list(session.scalars(select(Promotion).where(Promotion.start_date <= end,
                                                            Promotion.end_date >= start)))
    return fit_observations(plan.week_start, orders, _expectations(session), stores, skus,
                            promotions, _groups(session))


def fit_observations(week_start, orders, expected, stores, skus, promotions, groups):
    """Fit recorded or counterfactual observations through the same preparation path.

    Orders are (date, store_id, sku, ordered_units) rows. No database is changed.
    """
    end = week_start - timedelta(days=1)
    recent_start = end - timedelta(days=13)
    start = recent_start - timedelta(days=56)
    if expected.empty:
        result = fit_units([], [])
        result['method']['status'] = 'issued_expectations_unavailable'
        return result
    expected = expected.copy()
    expected['date'] = pd.to_datetime(expected.date).dt.date
    expected = expected[expected.date.between(start, end)]
    actual = {(pd.Timestamp(d).date(), store, sku): float(a) for d, store, sku, a in orders
              if start <= pd.Timestamp(d).date() <= end}
    excluded = defaultdict(set)
    for promo in promotions:
        day = max(start, promo.start_date)
        while day <= min(end, promo.end_date):
            excluded[promo.sku].add(day)
            day += timedelta(days=1)
    forecast = {}
    for r in expected.itertuples():
        if r.store_id in stores and r.sku in skus and np.isfinite(r.mean) and r.mean >= 0:
            forecast[(r.date, r.store_id, r.sku)] = float(r.mean)
    units = []
    skipped = []
    for name in skus:
        for area in sorted(set(stores.values())):
            store_ids = sorted(s for s, d in stores.items() if d == area)
            dates = [d.date() for d in pd.date_range(start, end) if d.date() not in excluded[name]]
            recent = [d for d in dates if d >= recent_start]
            baseline = [d for d in dates if d < recent_start]
            keys = [(d, s, name) for d in dates for s in store_ids]
            missing = [k for k in keys if k not in actual or k not in forecast]
            if missing or len(recent) == 0 or len(baseline) == 0:
                skipped.append({'sku': name, 'district': area, 'reason': 'missing_rows_or_short_window',
                                'missing_rows': len(missing), 'recent_days': len(recent),
                                'baseline_days': len(baseline)})
                continue
            caps = {s: float(np.quantile([actual[(d, s, name)] for d in dates], .99)) for s in store_ids}
            clipped = []
            daily = {}
            for d in dates:
                a = 0.
                e = 0.
                for s in store_ids:
                    value = actual[(d, s, name)]
                    if value > caps[s]:
                        clipped.append({'date': d.isoformat(), 'store_id': s, 'raw': value, 'cap': caps[s]})
                    a += min(value, caps[s])
                    e += forecast[(d, s, name)]
                daily[d] = (a, e)
            ar, er = (sum(daily[d][i] for d in recent) for i in (0, 1))
            ab, eb = (sum(daily[d][i] for d in baseline) for i in (0, 1))
            weekly = []
            for first in range(0, len(baseline), 7):
                days = baseline[first:first + 7]
                if len(days) == 7:
                    wa = sum(daily[d][0] for d in days)
                    we = sum(daily[d][1] for d in days)
                    if we > 0:
                        weekly.append((wa - we) / sqrt(we))
            phi = max(1., float(np.var(weekly, ddof=1))) if len(weekly) >= 2 else 1.
            units.append({'sku': name, 'district': area,
                          'y': log((ar + .5) / (er + .5)) - log((ab + .5) / (eb + .5)),
                          'v': phi * (1 / (ar + .5) + 1 / (ab + .5)),
                          'recent_A': ar, 'recent_E': er, 'baseline_A': ab, 'baseline_E': eb,
                          'expected_recent': er, 'phi': phi, 'recent_days': len(recent),
                          'baseline_days': len(baseline),
                          'promotion_exclusions': sorted(d.isoformat() for d in excluded[name] if start <= d <= end),
                          'winsorised': clipped, 'winsor_caps': caps})
    result = fit_units(units, groups)
    result['method'].update(window_recent=[recent_start.isoformat(), end.isoformat()],
                            window_baseline=[start.isoformat(), (recent_start - timedelta(days=1)).isoformat()],
                            unit_definition='SKU × district; complete observed and issued rows; at least one eligible day in each window',
                            winsorisation='per store/SKU 99th percentile across eligible 70-day history before aggregation',
                            overdispersion='sample variance of seven-day (A-E)/sqrt(E) baseline residuals, floored at 1',
                            skipped_units=skipped)
    return result
