"""Bounded, read-only matched-space preparation for a Play job."""
from __future__ import annotations

from . import play

LOW, HIGH = 0.50, 0.98
TOLERANCE = 0.02
MAX_REPLAYS = 6


def prepare(pid, week_start):
    actual = play.simulate(pid, week_start)
    baseline_run = actual['runs']['baseline']
    baseline_summary = actual['summary']['baseline']
    target = baseline_summary['avg_pallets']
    cohort_cache = {}
    attempts = []
    candidates = []

    def record(service, result):
        summary = result['summary']['scoop']
        gap = abs(summary['avg_pallets'] - target) / max(abs(target), 1e-9)
        attempts.append({'service_level': service, 'avg_pallets': summary['avg_pallets'],
                         'lost_units': summary['lost_units'],
                         'stockout_sku_days': summary['stockout_sku_days'],
                         'lost_margin': summary['lost_margin']})
        candidates.append((gap, result, service))
        return summary['avg_pallets'], gap

    # The actual approved-order replay is a measured point, and counts toward the cap.
    original_service = None
    record(original_service, actual)
    # An automatic margin policy has SKU-specific critical ratios, not one
    # explicit service point. Measure the bounded service candidates even when
    # that policy happens to sit inside the space tolerance already.
    if len(attempts) < MAX_REPLAYS:
        low = high = None
        for service in (LOW, HIGH):
            result = play.simulate(pid, week_start, _service_level=service,
                                   _baseline_run=baseline_run, _cohort_cache=cohort_cache)
            measured = record(service, result)
            if service == LOW:
                low = measured
            else:
                high = measured
            if measured[1] <= TOLERANCE:
                break
        if high is not None and min(c[0] for c in candidates[1:]) > TOLERANCE:
            lo_service, hi_service = LOW, HIGH
            lo_pallets, hi_pallets = low[0], high[0]
            # With both bounds on one side, the reachable interval has been measured.
            while len(attempts) < MAX_REPLAYS and (lo_pallets - target) * (hi_pallets - target) < 0:
                service = (lo_service + hi_service) / 2
                result = play.simulate(pid, week_start, _service_level=service,
                                       _baseline_run=baseline_run, _cohort_cache=cohort_cache)
                pallets, gap = record(service, result)
                if gap <= TOLERANCE:
                    break
                if (lo_pallets - target) * (pallets - target) <= 0:
                    hi_service, hi_pallets = service, pallets
                else:
                    lo_service, lo_pallets = service, pallets

    gap, selected, service = min(candidates, key=lambda x: x[0])
    within = gap <= TOLERANCE
    matched = {
        'status': 'matched' if within else 'closest',
        'within_tolerance': within, 'tolerance': TOLERANCE,
        'service_level': service, 'relative_pallet_gap': gap,
        'simulation_count': len(attempts),
        'summary': {'scoop': selected['summary']['scoop'], 'baseline': baseline_summary},
        'runs': {'scoop': {'daily': selected['runs']['scoop']['daily'],
                           'per_sku': selected['runs']['scoop']['per_sku']}},
        'attempts': attempts,
    }
    if not within:
        matched['limit_reason'] = ('evaluation_limit' if len(attempts) >= MAX_REPLAYS else
                                   'service_bounds')
    return {**actual, 'matched': matched}
