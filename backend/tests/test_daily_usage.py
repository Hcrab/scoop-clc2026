"""The public allowance counts actual provider attempts across all visitors."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from scoop.ai import usage


def test_hong_kong_midnight():
    assert usage.daily_window(datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc)) == (
        '2026-10-21T16:00:00+00:00', '2026-10-22T16:00:00+00:00')
    assert usage.daily_window(datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc)) == (
        '2026-10-22T16:00:00+00:00', '2026-10-23T16:00:00+00:00')


def test_shared_daily_limit_is_atomic_and_persistent(tmp_path, monkeypatch):
    path = tmp_path / 'usage.sqlite3'
    monkeypatch.setattr(usage, 'settings', replace(usage.settings,
        llm_daily_max_calls=2, llm_max_calls=120, llm_budget_usd=3))

    def attempt(_):
        try:
            return usage.reserve('gemini-3.8-flash', 'digest-only', 10, 10, path=path)
        except usage.UsageLimit:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(r is not None for r in results) == 2
    stats = usage.summary(path=path)
    assert stats['daily_calls'] == 2 and stats['daily_remaining'] == 0
    # Finishing/reopening the database cannot reset the counter; failed provider
    # attempts also remain charged against the request cap.
    for rid in filter(None, results):
        usage.finish(rid, {}, 'transport_error', path=path)
    with pytest.raises(usage.UsageLimit, match='daily'):
        usage.reserve('gemini-3.8-flash', 'new-digest', 10, 10, path=path)
    # Move yesterday's records out of today's window: the next day is usable.
    with usage.ledger(path) as db:
        db.execute("UPDATE calls SET created_at='2020-01-01T00:00:00+00:00'")
    assert usage.summary(path=path)['daily_calls'] == 0
    assert usage.reserve('gemini-3.8-flash', 'next-day', 10, 10, path=path)
