"""Intraday placement must conserve every daily SKU flow and event boundary."""

import copy
from datetime import date

import pytest

from scoop import intraday, play
from scoop.config import DAYTIME_REQUEST_WEIGHTS, DEMAND_HOURLY_WEIGHTS, SUPPLIER_WINDOWS
from test_play import played_week


@pytest.mark.parametrize('policy', ['scoop', 'baseline'])
def test_hourly_reconciles_every_day_sku_and_policy(played_week, policy):
    result = played_week
    per = result['runs'][policy]['per_sku']
    hourly = result['runs'][policy]['hourly']
    opening = result['intraday']['opening_on_hand']
    for day in range(result['days']):
        for j, sku in enumerate(result['skus']):
            start = opening[j] if day == 0 else per['on_hand'][day - 1][j]
            end = per['on_hand'][day][j]
            for key in ('demand', 'shipped', 'lost', 'arrived'):
                assert all(hourly[key][day * 24 + h][j] >= 0 for h in range(24))
                assert sum(hourly[key][day * 24 + h][j] for h in range(24)) == pytest.approx(
                    per[key][day][j], abs=1e-9), (policy, sku, day, key)
            assert sum(hourly['on_hand_delta'][day * 24 + h][j] for h in range(24)) == pytest.approx(end - start)
            for h in range(24):
                row = day * 24 + h
                before = start if h == 0 else hourly['on_hand'][row - 1][j]
                assert hourly['on_hand'][row][j] == pytest.approx(
                    before + hourly['arrived'][row][j] - hourly['shipped'][row][j])
                assert hourly['on_hand_delta'][row][j] == pytest.approx(hourly['on_hand'][row][j] - before)
            assert hourly['on_hand'][day * 24 + 23][j] == pytest.approx(end)


def test_profile_arrivals_and_events_are_timed_and_stable(played_week):
    result = played_week
    profile = result['intraday']
    assert profile['minutes'] == list(range(0, 1441, 10))
    assert len(profile['demand_cdf']) == len(profile['dispatch_cdf']) == 145
    assert profile['demand_cdf'][0] == profile['dispatch_cdf'][0] == 0
    assert profile['demand_cdf'][-1] == profile['dispatch_cdf'][-1] == 1
    for key in ('demand_cdf', 'dispatch_cdf'):
        assert all(0 <= a <= b <= 1 for a, b in zip(profile[key], profile[key][1:]))
    assert len(DAYTIME_REQUEST_WEIGHTS) == len(DEMAND_HOURLY_WEIGHTS) == 24
    assert all(weight > 0 for weight in DEMAND_HOURLY_WEIGHTS[:22])
    assert DEMAND_HOURLY_WEIGHTS[22:] == (0, 0)
    assert sum(DEMAND_HOURLY_WEIGHTS) == pytest.approx(1)
    assert all(new == pytest.approx(.9 * old + (.1 / 22 if hour < 22 else 0))
               for hour, (old, new) in enumerate(zip(DAYTIME_REQUEST_WEIGHTS, DEMAND_HOURLY_WEIGHTS)))
    assert profile['demand_cdf'][22 * 6] == 1
    assert all(dispatch <= requested for dispatch, requested in zip(
        profile['dispatch_cdf'], profile['demand_cdf']))
    assert 0 < profile['demand_cdf'][5] < profile['demand_cdf'][60]
    for day, receipts in enumerate(profile['arrival_minutes']):
        for j, supplier in enumerate(('SUP01', 'SUP02')):
            lo, hi = SUPPLIER_WINDOWS[supplier]
            assert lo <= receipts[j] <= hi and receipts[j] % 10 == 0
    for event in result['events']:
        assert event['minute'] in range(0, 1440, 10)
        assert event['time'] == f"{event['minute'] // 60:02d}:{event['minute'] % 60:02d}"
        assert event['at'] == f"{event['date']}T{event['time']}:00"
        assert event['id']
        if event['kind'] == 'arrival':
            day = result['dates'].index(event['date'])
            j = result['skus'].index(event['sku'])
            assert event['minute'] == profile['arrival_minutes'][day][j]
            assert event['units'] == result['runs'][event['policy']]['per_sku']['arrived'][day][j]
    assert result['events'] == sorted(result['events'], key=lambda item: (item['at'], item['id']))
    before = copy.deepcopy([(e['id'], e['at']) for e in result['events']])
    play._CACHE.clear()
    replay = play.simulate('test-plan', date.fromisoformat(result['start']), days=result['days'])
    assert before == [(e['id'], e['at']) for e in replay['events']]
    for policy in ('scoop', 'baseline'):
        assert result['runs'][policy]['daily'] == replay['runs'][policy]['daily']
        assert result['runs'][policy]['per_sku'] == replay['runs'][policy]['per_sku']


def test_morning_receipt_cannot_erase_earlier_cumulative_loss():
    receipt = 10 * 60
    curve = intraday.cumulative_loss(100, 0, 98, receipt, 2)
    before = receipt // 10 - 1
    assert curve[before] == 2  # Early requests can exceed the final daily loss.
    assert curve[before + 1] == 2  # The morning receipt cannot undo them.
    assert all(0 <= a <= b <= 2 for a, b in zip(curve, curve[1:]))
    assert curve[-1] == 2


def test_enrich_preserves_daily_physical_results_and_summary(played_week):
    result = copy.deepcopy(played_week)
    physical = copy.deepcopy({
        'summary': result['summary'],
        'events': result['events'],
        'runs': {policy: {key: run[key] for key in ('daily', 'per_sku')}
                 for policy, run in result['runs'].items()},
    })
    intraday.enrich(result, ['SUP01', 'SUP02'])
    assert result['summary'] == physical['summary']
    assert result['events'] == physical['events']
    for policy, run in result['runs'].items():
        for key in ('daily', 'per_sku'):
            assert run[key] == physical['runs'][policy][key]


def test_stockout_events_use_first_strict_exceedance(played_week):
    result = played_week
    profile = result['intraday']
    for event in result['events']:
        if event['kind'] not in ('stockout', 'kept'):
            continue
        policy = 'scoop' if event['kind'] == 'stockout' else 'baseline'
        day = result['dates'].index(event['date'])
        j = result['skus'].index(event['sku'])
        per = result['runs'][policy]['per_sku']
        assert per['lost'][day][j] > 0
        if event['kind'] == 'kept':
            assert result['runs']['scoop']['per_sku']['lost'][day][j] == 0
        opening = profile['opening_on_hand'][j] if day == 0 else per['on_hand'][day - 1][j]
        arrival = per['arrived'][day][j]
        receipt = profile['arrival_minutes'][day][j]
        demand = per['demand'][day][j]
        exceeding = [minute for k, minute in enumerate(profile['minutes'][:-1])
                     if demand * profile['demand_cdf'][k] > opening + (arrival if minute >= receipt else 0) + 1e-9]
        assert exceeding and event['minute'] == exceeding[0]
        assert event['order_dates'] is not None and event['rule_order_dates'] is not None
