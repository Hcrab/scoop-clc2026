"""Read-only conditional cohort tree and two-level empirical Bayes demand effects."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
from math import exp, log, sqrt

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..models import Product, Promotion, Store, StoreOrder, Setting

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


def _permutation_orders(skus, districts, rng):
    """Tag tests exchange SKU vectors; district tests exchange within SKU.

    Match district support when a node has incomplete SKU vectors. This keeps
    missing districts missing instead of imputing or breaking a product block.
    Both returned indices move y and v together.
    """
    by_sku = defaultdict(list)
    for index, name in enumerate(skus):
        by_sku[name].append(index)
    signatures = defaultdict(list)
    district_order = np.arange(len(skus))
    for indices in by_sku.values():
        ordered = sorted(indices, key=lambda i: districts[i])
        signatures[tuple(districts[i] for i in ordered)].append(ordered)
        district_order[ordered] = rng.permutation(ordered)
    tag_order = np.arange(len(skus))
    for blocks in signatures.values():
        for target, source in zip(blocks, rng.permutation(len(blocks))):
            tag_order[target] = blocks[source]
    return tag_order, district_order


def fit_units(units, groups, *, split_alpha=.05):
    """Fit SKU/district observations with block-aware split permutations.

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
                tag_order, district_order = _permutation_orders(sku[indices], district[indices], rng)
                tag_y, tag_v = y[indices][tag_order], v[indices][tag_order]
                district_y, district_v = y[indices][district_order], v[indices][district_order]
                maximum.append(max(_gain(district_y, district_v, mask) if key.startswith('district:')
                                   else _gain(tag_y, tag_v, mask) for key, mask in choices))
            p = float(np.mean(np.array(maximum) >= observed))
            tested.append({'path': path, 'candidate_count': len(choices), 'gain': observed,
                           'split_tag': choices[winner][0], 'p_value': p, 'permutations': PERMUTATIONS})
            if p < split_alpha:
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
                       'permutations': PERMUTATIONS, 'seed': SEED, 'split_alpha': split_alpha,
                       'permutation_scheme': 'product tags: whole SKU district vectors within equal-support strata; district tags: districts within each SKU; y and v paired; max across all candidates',
                       'tested_nodes': tested, 'eb': 'two-level DerSimonian-Laird',
                       'sku_covariance': 'district demand weights; conditional variances independent; shared leaf posterior covariance',
                       'projection': 'level, no extrapolation'}}


def current_expectations(plan):
    """Re-score historical windows with the model active for this plan.

    Weather features retain each day's issued forecast. A newly trained model
    can absorb an earlier change instead of carrying an old factor indefinitely.
    """
    from .runs import artifacts
    from .forecast import build_features, issued_daily_weather
    art = artifacts()
    model = art.run_for(plan.week_start).model
    dates = pd.date_range(plan.week_start - timedelta(days=70),
                          plan.week_start - timedelta(days=1))
    features = build_features(art.static, dates, weather=issued_daily_weather(art.static, dates))
    result = model.predict(features, mean_only=True)
    result.attrs['model_version'] = model.version
    return result


def _attach_drilldowns(result, chart_rows, groups):
    """Preserve the actual fitted prefix and its sibling from eligible history."""
    catalog = ({key: set(getattr(group, 'skus', group)) for key, group in groups.items()}
               if isinstance(groups, dict) else {group.id: set(group.skus) for group in groups})
    rows = result['units']

    def aggregate(indices):
        totals = {}
        for i in indices:
            unit = rows[i]
            for day, (observed, predicted) in chart_rows[(unit['sku'], unit['district'])].items():
                value = totals.setdefault(day, [0., 0.])
                value[0] += observed
                value[1] += predicted
        return [{'date': day.isoformat(), 'requested_units': totals[day][0],
                 'expected_units': totals[day][1]} for day in sorted(totals)]

    def effect(indices):
        weights = np.array([1 / rows[i]['v'] for i in indices])
        values = np.array([rows[i]['y'] for i in indices])
        return float(np.expm1(np.dot(weights, values) / weights.sum()) * 100)

    all_indices = list(range(len(rows)))
    if not all_indices:
        return
    root = {'effect_pct': effect(all_indices), 'daily': aggregate(all_indices)}
    for leaf in result['leaves']:
        parent = all_indices
        steps = []
        for path in leaf['tag_path']:
            tag_id, included = path['id'], path['included']
            members = [i for i in parent if (rows[i]['district'] == tag_id.split(':', 1)[1]
                       if tag_id.startswith('district:') else rows[i]['sku'] in catalog[tag_id]) == included]
            member_set = set(members)
            rest = [i for i in parent if i not in member_set]
            steps.append({'tag_id': tag_id, 'included': included,
                          'effect_pct': effect(members), 'rest_effect_pct': effect(rest),
                          'daily': aggregate(members), 'rest_daily': aggregate(rest),
                          'sku_count': len({rows[i]['sku'] for i in members}),
                          'rest_sku_count': len({rows[i]['sku'] for i in rest})})
            parent = members
        leaf['drilldown'] = {'root': root, 'steps': steps}


def fit(plan, session=None):
    """Refit recorded observations against the current plan's forecast model."""
    if session is None:
        from ..db import SessionLocal
        with SessionLocal() as own:
            return fit(plan, own)
    from ..ai.exploration_tools import _groups

    end = plan.week_start - timedelta(days=1)
    recent_start = end - timedelta(days=13)
    start = recent_start - timedelta(days=56)
    stores = {s.id: s.district for s in session.scalars(select(Store))}
    skus = sorted(session.scalars(select(Product.sku)))
    orders = session.execute(select(StoreOrder.date, StoreOrder.store_id, StoreOrder.sku, StoreOrder.ordered_units)
                             .where(StoreOrder.date.between(start, end))).all()
    promotions = list(session.scalars(select(Promotion).where(Promotion.start_date <= end,
                                                            Promotion.end_date >= start)))
    expected = current_expectations(plan)
    from ..demo_config import DEMO_SEED, DEMO_COHORT_ALPHA
    seed = session.get(Setting, 'seed')
    split_alpha = DEMO_COHORT_ALPHA if seed and seed.value == str(DEMO_SEED) else .05
    result = fit_observations(plan.week_start, orders, expected, stores, skus,
                              promotions, _groups(session), split_alpha=split_alpha)
    result['method']['expectation_basis'] = 'current_model_rescored_with_historical_issued_weather'
    result['method']['model_version'] = expected.attrs.get('model_version')
    return result


def fit_observations(week_start, orders, expected, stores, skus, promotions, groups, *, split_alpha=.05):
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
    chart_rows = {}
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
            chart_rows[(name, area)] = {d: (sum(actual[(d,store,name)] for store in store_ids), daily[d][1]) for d in dates}
            ar, er = (sum(daily[d][i] for d in recent) for i in (0, 1))
            ab, eb = (sum(daily[d][i] for d in baseline) for i in (0, 1))
            weekly = []
            weekly_log_errors = []
            weekly_sampling_variances = []
            for first in range(0, len(baseline), 7):
                days = baseline[first:first + 7]
                if len(days) == 7:
                    wa = sum(daily[d][0] for d in days)
                    we = sum(daily[d][1] for d in days)
                    if we > 0:
                        weekly.append((wa - we) / sqrt(we))
                        weekly_log_errors.append(log((wa + .5) / (we + .5)))
                        weekly_sampling_variances.append(1 / (we + .5))
            phi = max(1., float(np.var(weekly, ddof=1))) if len(weekly) >= 2 else 1.
            # Baseline seven-day issued-weather residuals estimate the forecast's
            # systematic log-rate error beyond count sampling. Scale from a
            # weekly residual to the recent and baseline window averages.
            systematic_weekly = (max(0., float(np.var(weekly_log_errors, ddof=1))
                                     - float(np.mean(weekly_sampling_variances)))
                                 if len(weekly_log_errors) >= 2 else 0.)
            forecast_error_v = systematic_weekly * (7 / len(recent) + 1 / len(weekly_log_errors)) if weekly_log_errors else 0.
            units.append({'sku': name, 'district': area,
                          'y': log((ar + .5) / (er + .5)) - log((ab + .5) / (eb + .5)),
                          'v': phi * (1 / (ar + .5) + 1 / (ab + .5)) + forecast_error_v,
                          'forecast_error_v': forecast_error_v,
                          'forecast_error_weekly_log_variance': systematic_weekly,
                          'recent_A': ar, 'recent_E': er, 'baseline_A': ab, 'baseline_E': eb,
                          'expected_recent': er, 'phi': phi, 'recent_days': len(recent),
                          'baseline_days': len(baseline),
                          'promotion_exclusions': sorted(d.isoformat() for d in excluded[name] if start <= d <= end),
                          'winsorised': clipped, 'winsor_caps': caps})
    result = fit_units(units, groups, split_alpha=split_alpha)
    _attach_drilldowns(result, chart_rows, groups)
    for leaf in result['leaves']:
        totals = {}
        for unit in result['units']:
            if unit['leaf_id'] != leaf['id']:
                continue
            for day, (observed, predicted) in chart_rows[(unit['sku'], unit['district'])].items():
                row = totals.setdefault(day, {'date':day.isoformat(), 'requested_units':0., 'expected_units':0., 'unit_count':0})
                row['requested_units'] += observed
                row['expected_units'] += predicted
                row['unit_count'] += 1
        leaf['daily'] = [totals[day] for day in sorted(totals)]
        leaf['series_scope'] = 'Observed requests and current-model expectations for eligible SKU/district units; SKU promotion days excluded. Observed chart values are not winsorised.'
    result['method'].update(window_recent=[recent_start.isoformat(), end.isoformat()],
                            window_baseline=[start.isoformat(), (recent_start - timedelta(days=1)).isoformat()],
                            unit_definition='SKU × district; complete observed and issued rows; at least one eligible day in each window',
                            winsorisation='per store/SKU 99th percentile across eligible 70-day history before aggregation',
                            overdispersion='sample variance of seven-day (A-E)/sqrt(E) baseline residuals, floored at 1',
                            forecast_error_variance='Per SKU/district, sample variance of eligible baseline seven-day log((A+0.5)/(E+0.5)) current-model residuals minus mean 1/(E+0.5) count-sampling variance, clipped at zero; log-rate units squared. Add this weekly systematic variance times (7/recent eligible days + 1/baseline eligible weeks) to each unit log-change variance. Uses historical issued weather and baseline outcomes only; part of the baseline may be in the current model training period. No percentage floor.',
                            drilldown_effect='Inverse-variance weighted mean unit log change transformed with expm1 × 100 at each actual tree prefix, before leaf and SKU shrinkage. Daily requests are raw eligible observations; siblings are within the same parent.',
                            skipped_units=skipped)
    return result
