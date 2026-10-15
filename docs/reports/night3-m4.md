# M4 — Daily values during Play

During Play, request and shortage widgets show **Today so far**. Each completed day remains a full daily observation; the unfinished day is a hollow point excluded from the connected lines. Expected requests use the same elapsed-day fraction. Fill rate remains **Pending dispatch** until dispatch starts, rather than treating an unstarted dispatch as a failed service day.

The original illustrative request profile contained no overnight requests. The presentation profile now combines 90% of that daytime shape with 10% uniform background requests across 24 hours. Daily demand, order quantities, inventory settlement, losses and policy comparisons are unchanged. Supplier receipt windows and evening dispatch are retained. This is an illustrative clock allocation, not measured hourly demand. The replay's existing final tick, 23:50, displays settled daily arrays; Results also uses those daily arrays.

Cumulative shortage is capped by the settled daily loss and cannot decrease after a receipt. Backend hourly increments and the frontend ten-minute point use the same running maximum. Both policies use this presentation rule. Cached jobs are invalidated with `same-cold-store-play-v6`.

## Verification

- ✅ Backend: **27 passed** across `test_intraday.py`, `test_play.py`, `test_play_comparison.py`, `test_simulation_jobs.py`; output `reports/m4-tests.txt`. Covers profile conservation, receipt timing, nonnegative hourly increments, monotone cumulative loss, unchanged physical arrays and summaries, and shared capacity.
- ✅ Frontend: **4 passed**, `frontend/tests/widget-today.test.cjs`; output `reports/m4-frontend-python.txt`. Covers growing ten-minute totals, full daily closing values, pending dispatch, monotone shortages and partial markers outside the connected lines.
- ✅ Production build: `reports/m4-build.txt`.
- ✅ Real browser: **1 passed (2.7 min)**, `reports/m4-browser.txt` and `reports/m4-browser.json`. At **29 Jul 00:50**, cohort requests show **3** and **4 units**, stock **74,327 units**, and cold store **51.8 pallets**. The screenshot `docs/screenshots/m4-midnight.png` was personally inspected: completed-day lines stop before the hollow current-day point; no connected zero drop. The closing tick shows full daily request totals, removes partial markers, preserves saved orders and produces no page errors. Demand, shipment and loss arrays still agree with M1. The test restores the clean Report state without provider calls.

The first browser run reached the midnight capture and full-day close, then failed an extra comparison that required inventory and later orders to equal M1's **60-pallet** replay. The current world uses **66 pallets** after M2. Request, shipment and loss arrays remain comparable; capacity-sensitive inventory and later order differences are retained as context in `reports/m4-browser.json`. The dedicated enrichment test above verifies that adding intraday presentation leaves the exact same-capacity physical arrays and summary untouched.
