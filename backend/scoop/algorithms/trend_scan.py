"""Read-only, family-adjusted exploration of catalog AND cohorts.

This is an approximate screening test, not the planner's calibrated CUSUM.
Issued monthly forecasts are reused; no fitting, network calls or writes occur.
"""
from datetime import timedelta
from hashlib import sha256
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import t
from sqlalchemy import select

from ..models import Product, Store, StoreOrder

METHOD = ('Recent 14-day fractional forecast residual versus up to 56 earlier days; '
          'Bartlett Newey-West variance (7 lags), conservative weekly-block t degrees '
          'of freedom, and Benjamini-Yekutieli adjustment over every eligible unique '
          'cohort/district scope. Approximate exploratory evidence: calibration may '
          'contain shifts; forecast error, short history and nonstationarity can affect results. '
          'Issued monthly expectations incorporate the existing weather model; no causal attribution.')


def _candidates(catalog, skus):
    """Enumerate every cross-dimension 1/2/3-tag intersection, deduplicating members."""
    entries = sorted(catalog.values(), key=lambda g: g.id)
    members = {g.id: frozenset(g.skus) & skus for g in entries}
    unique = {}
    for size in (1, 2, 3):
        for choice in combinations(entries, size):
            if len({g.dimension for g in choice}) != size:
                continue
            cohort = frozenset.intersection(*(members[g.id] for g in choice))
            if len(cohort) < 3:
                continue
            ids = tuple(g.id for g in choice)
            if cohort not in unique:
                unique[cohort] = {'ids': ids, 'aliases': []}
            else:
                unique[cohort]['aliases'].append(ids)
    return sorted(unique.items(), key=lambda row: row[1]['ids'])


def _long_run_variance(values):
    """Positive conservative HAC floor prevents negative covariance cancellation."""
    centered = values - values.mean()
    n = len(values)
    variance = float(centered @ centered / max(1, n - 1))
    estimate = variance
    for lag in range(1, min(7, n - 1) + 1):
        estimate += 2 * (1 - lag / 8) * float(centered[lag:] @ centered[:-lag] / n)
    return max(variance, estimate)


def _measure(a, e, observed, expected_coverage):
    recent = np.arange(len(a)) >= len(a) - 14
    valid = (e > 0) & observed & (expected_coverage >= .95)
    prior = valid & ~recent
    live = valid & recent
    if prior.sum() < 28 or live.sum() != 14:
        return None
    residual = np.divide(a - e, e, out=np.zeros_like(e), where=e > 0)
    before, now = residual[prior], residual[live]
    shift = float(now.mean() - before.mean())
    # Include recent variance so erratic current activity does not look persistent.
    # The Poisson-style floor keeps a perfectly flat small-volume history finite.
    variance = max(_long_run_variance(before), _long_run_variance(now),
                   float(np.mean(1 / e[valid])))
    se = float(np.sqrt(variance * (1 / len(before) + 1 / len(now))))
    statistic = abs(shift) / se
    df = max(3, len(before) // 7 - 1)
    p = float(2 * t.sf(statistic, df))
    direction = 1 if shift >= 0 else -1
    persistence = float(np.mean(direction * (now - before.mean()) > 0))
    weekly = [float(now[:7].mean() - before.mean()), float(now[7:].mean() - before.mean())]
    requested, forecast = float(a[recent].sum()), float(e[recent].sum())
    return {'requested_units': requested, 'expected_units': forecast,
            'excess_units': requested - forecast,
            'deviation_pct': 100 * (requested / forecast - 1),
            'shift': shift, 'se': se, 'statistic': statistic, 'p': p,
            'calibration_days': int(prior.sum()), 'baseline_residual_pct': float(before.mean() * 100),
            'persistence': persistence, 'weekly_shift_pct': [v * 100 for v in weekly],
            'weekly_consistent': bool(all(direction * v > 0 for v in weekly))}


def _adjust(pvalues):
    """BY permits dependence between overlapping scopes, given valid marginal p's."""
    p = np.asarray(pvalues)
    if not len(p):
        return p
    order = np.argsort(p, kind='stable')
    adjusted = p[order] * len(p) * np.sum(1 / np.arange(1, len(p) + 1)) / np.arange(1, len(p) + 1)
    result = np.empty_like(p)
    result[order] = np.minimum(1, np.minimum.accumulate(adjusted[::-1])[::-1])
    return result


def scan(session, plan):
    """Return up to 40 diverse signals, with all-family adjustment before selection."""
    # Lazy import keeps the algorithm importable without an AI runtime dependency.
    from ..ai.exploration_tools import _groups, _expectations

    cutoff = plan.week_start - timedelta(days=1)
    start = cutoff - timedelta(days=13)
    history_start = start - timedelta(days=56)
    result = {'status': 'unavailable', 'method': METHOD, 'window_start': start.isoformat(),
              'window_end': cutoff.isoformat(), 'tested_count': 0, 'items': []}
    try:
        expected = _expectations(session)
    except (ValueError, FileNotFoundError):
        return result
    if expected.empty or not {'date', 'store_id', 'sku', 'mean'} <= set(expected.columns):
        return result
    skus = sorted(session.scalars(select(Product.sku).order_by(Product.sku)))
    stores = {s.id: s.district for s in session.scalars(select(Store).order_by(Store.id))}
    catalog = _groups(session)
    candidates = _candidates(catalog, set(skus))
    if not candidates or not stores:
        return result
    dates = pd.date_range(history_start, cutoff)
    actual = pd.DataFrame(session.execute(select(StoreOrder.date, StoreOrder.store_id,
                          StoreOrder.sku, StoreOrder.ordered_units).where(
                          StoreOrder.date.between(history_start, cutoff))).all(),
                          columns=['date', 'store_id', 'sku', 'ordered_units'])
    expected = expected.copy()
    for frame in (actual, expected):
        frame['date'] = pd.to_datetime(frame.date)
        frame['district'] = frame.store_id.map(stores)
    expected = expected[expected.date.between(dates[0], dates[-1]) &
                        expected.sku.isin(skus) & expected.district.notna()].copy()
    expected['mean'] = pd.to_numeric(expected['mean'], errors='coerce')
    # A missing row is missing evidence, not a forecast of zero.
    expected = expected[np.isfinite(expected['mean']) & (expected['mean'] >= 0)]
    if expected.empty:
        return result
    actual = actual[actual.sku.isin(skus) & actual.district.notna()]
    mask = np.array([[sku in cohort for sku in skus] for cohort, _ in candidates], dtype=float)
    all_districts = sorted(set(stores.values()))
    scopes = [all_districts] + [[d] for d in all_districts] if len(all_districts) > 1 else [all_districts]
    tested = []
    for districts in scopes:
        def matrix(frame, value, reducer='sum'):
            part = frame[frame.district.isin(districts)]
            return part.pivot_table(index='date', columns='sku', values=value,
                                    aggfunc=reducer).reindex(index=dates, columns=skus).fillna(0).to_numpy(float).T
        # One aggregation per scope, followed by matrix multiplication for all cohorts.
        a = mask @ matrix(actual, 'ordered_units')
        e = mask @ matrix(expected, 'mean')
        counts = {d: sum(v == d for v in stores.values()) for d in districts}
        store_count = sum(counts.values())
        valid_rows = expected.drop_duplicates(['date', 'store_id', 'sku'])
        row_counts = mask @ matrix(valid_rows.assign(_present=1.), '_present')
        actual_rows = actual.drop_duplicates(['date', 'store_id', 'sku'])
        actual_counts = mask @ matrix(actual_rows.assign(_present=1.), '_present')
        coverage = row_counts / (mask.sum(axis=1)[:, None] * store_count)
        observed = actual_counts / (mask.sum(axis=1)[:, None] * store_count) >= .95
        for i, (cohort, definition) in enumerate(candidates):
            stats = _measure(a[i], e[i], observed[i], coverage[i])
            if stats is not None:
                tested.append({'cohort': cohort, 'definition': definition, 'districts': districts,
                               'a': a[i], 'e': e[i], 'stats': stats,
                               'coverage': float(coverage[i, -14:].min())})
    result.update(status='ready' if tested else 'unavailable', tested_count=len(tested))
    if not tested:
        return result
    qvalues = _adjust([row['stats']['p'] for row in tested])
    lookup = {(row['cohort'], tuple(row['districts'])): row for row in tested}
    signals = []
    for row, q in zip(tested, qvalues):
        stats = row['stats']
        ids = row['definition']['ids']
        parents = []
        for parent_ids in combinations(ids, max(1, len(ids) - 1)) if len(ids) > 1 else []:
            cohort = frozenset.intersection(*(frozenset(catalog[g].skus) for g in parent_ids)) & set(skus)
            parent = lookup.get((cohort, tuple(row['districts'])))
            if parent:
                ps = parent['stats']
                parents.append({'name': ' AND '.join(catalog[g].name for g in parent_ids),
                                'group_ids': list(parent_ids), **{k: ps[k] for k in
                                ('requested_units', 'expected_units', 'deviation_pct')}})
        informative = bool(parents and all(abs(stats['deviation_pct'] - p['deviation_pct']) >
                                           stats['se'] * 100 for p in parents))
        # No fixed business percentage threshold: rank by calibrated shift and impact.
        if stats['statistic'] < 1.5 or stats['persistence'] < .5:
            continue
        score = float(np.log1p(abs(stats['excess_units'])) * np.log1p(stats['statistic']) *
                      stats['persistence'] * (1.2 if informative else 1.))
        row.update(q=float(q), parents=parents, informative=informative, score=score)
        signals.append(row)
    # Greedy overlap penalty keeps aliases/supersets and repeated districts from
    # consuming the first page, while distinct intersection effects survive.
    selected = []
    while signals and len(selected) < 40:
        def diversity_score(row):
            penalty = 1.
            for other in selected:
                overlap = len(row['cohort'] & other['cohort']) / min(len(row['cohort']), len(other['cohort']))
                same_effect = abs(row['stats']['deviation_pct'] - other['stats']['deviation_pct']) <= 100 * max(row['stats']['se'], other['stats']['se'])
                scope_overlap = bool(set(row['districts']) & set(other['districts']))
                if overlap > .8 and same_effect and scope_overlap:
                    penalty *= .2
            return row['score'] * penalty
        signals.sort(key=lambda r: (-diversity_score(r), r['definition']['ids'], r['districts']))
        selected.append(signals.pop(0))
    for row in selected:
        stats, ids = row['stats'], row['definition']['ids']
        names = ' AND '.join(catalog[g].name for g in ids)
        identity = '|'.join(sorted(row['cohort'])) + '::' + '|'.join(row['districts'])
        direction = 'up' if stats['shift'] >= 0 else 'down'
        clear = row['q'] <= .1 and stats['persistence'] >= .7 and stats['weekly_consistent']
        result['items'].append({'id': 'T' + sha256(identity.encode()).hexdigest()[:16],
            'name': names, 'group_ids': list(ids), 'kind': 'single' if len(ids) == 1 else 'combination',
            'level': 'clear' if clear else 'watch', 'direction': direction,
            'sku_count': len(row['cohort']), 'skus': sorted(row['cohort']), 'districts': row['districts'],
            **{k: stats[k] for k in ('requested_units', 'expected_units', 'excess_units', 'deviation_pct')},
            'q_value': row['q'], 'score': row['score'],
            'explanation': (f"Requests are {stats['deviation_pct']:+.1f}% versus issued expectations; "
                            f"forecast residual shifted {100 * stats['shift']:+.1f} percentage points "
                            f"from the prior {stats['calibration_days']} observed days."),
            'parents': row['parents'],
            'series': [{'date': day.date().isoformat(), 'requested_units': float(a), 'expected_units': float(e)}
                       for day, a, e in zip(dates[-28:], row['a'][-28:], row['e'][-28:])],
            'checks': {'exploratory': True, 'formal_validation': False, 'family_adjustment': 'Benjamini-Yekutieli',
                       'family_tested_count': len(tested), 'approximate_p_value': stats['p'],
                       'standard_error_pct': stats['se'] * 100, 'standardized_shift': stats['statistic'],
                       'calibration_days': stats['calibration_days'], 'calibration_start': history_start.isoformat(),
                       'calibration_end': (start - timedelta(days=1)).isoformat(),
                       'baseline_residual_pct': stats['baseline_residual_pct'],
                       'persistence': stats['persistence'], 'weekly_shift_pct': stats['weekly_shift_pct'],
                       'expected_row_coverage': row['coverage'], 'distinct_from_parents': row['informative'],
                       'equivalent_labels': [{'group_ids': list(alias), 'name': ' AND '.join(catalog[g].name for g in alias)}
                                             for alias in row['definition']['aliases']],
                       'serial_dependence': '7-lag HAC; weekly-block degrees of freedom; variance includes recent period',
                       'missing_data': 'Tests require 14 complete recent days and at least 28 prior days with >=95% actual and expected row coverage.'}})
    return result
