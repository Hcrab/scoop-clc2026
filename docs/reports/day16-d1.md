# D1 — stock health in Watch and Play

Accepted on `claude/scoop-prototype`, after starting at `a9786c4`. D2 has not started.

The four fixed tiles use a 28-day recorded period ending before the plan date. Play extends that same recorded period with elapsed Scoop requests, shipments and shortage product-days, while updating current stock and the observed peak with the clock. Before today's dispatch begins, fill remains through yesterday; it never shows a pending message. Low cover uses each product's trailing seven complete days of requested units and its supplier's lead time, with a strict less-than comparison. Missing/zero-demand cover is not counted as low cover.

Stock charts retain grey history and show the Scoop line in green, changing to amber below its safety reference and coral where the simulated products experience shortages. The blue line represents requests in the same units; days-cover charts use one day of demand as their reference. The safety reference uses trailing demand through the next known simulated arrival, falling back to supplier lead time where no arrival is scheduled. The historical safety reference is trailing demand × supplier lead time. Projected daily points appear separately after 12:00. Current stock keys stay current; flow keys use numeric yesterday values before dispatch.

## Acceptance evidence

| Check | Result and evidence |
|---|---|
| Watch tiles and defaults | ✅ `docs/screenshots/d1-watch.png`: four aligned fixed tiles and five detailed widgets; no loading state. |
| Midnight | ✅ `d1-midnight.png`: 29 Jul 00:50, 7.1 days stock cover, 100% yesterday service, 1,281 yesterday requests, 2.5 lowest cover and 51.8 pallets; zero partial points. |
| Noon | ✅ `d1-noon.png`: 29 Jul 12:40, five independent hollow projected values, complete-day lines remain separate. |
| Stock state | ✅ `d1-stock-state.png`: safe band, amber segments and eight coral shortage dots; stock key 3.4 days of cover, 5,445 units on hand. |
| Names / colours | ✅ `reports/d1-static-checks.txt` and browser assertions: removed names absent; simple-rule orange is Results-only. |
| Threshold and low-cover math | ✅ `reports/d1-final-frontend-python.txt`: 12 tests. Exact inclusive healthy boundaries, strict low-cover ranking and no baseline access are tested. |
| Persistence / history / feed | ✅ `reports/d1-final-backend-tests.txt`: 81 tests, 3 existing deprecation warnings. Fixed data with zero widgets, pre-plan cutoff, exact edit/Undo, AI default layout ownership, initial snapshots, grouped order totals, separate our-plan events and queue invalidation are covered. |
| Real UI | ✅ `reports/d1-browser.txt`: 1 passed, 1.7 minutes, no mocked responses or page errors. `d1-browser.json` includes list checks, actual keys, grouped order contents, source summary and exact widget/quantity restoration. |
| Build | ✅ `reports/d1-final-build.txt`: production build succeeds; Vite reports its bundle-size advisory at about 504 kB. |

All four screenshots were personally inspected. Numbers and titles align, chart units are consistent, the midnight frame has no artificial drop, the noon projection stays hollow, and the stock-state chart shows the actual alert colours. Detailed widgets retain their controls; the four fixed tiles have no edit/remove controls. The low-cover tile opens its product list.

## AI defaults, data and allowance

The report needed a new structured widget selection. Its existing evidence was reused in a finish-only authoring pass: no new exploration queries. Gemini 3.8 Flash returned five widgets, including the strawberry stock/service measures, chocolate-coated requests, lowest cover and cold-store use. Two saved widget names were corrected to describe the plotted metric (requests and current occupancy), with no numerical/threshold changes. Future authoring guidance now names those metrics accurately. The initial Reset snapshot includes the authored selection.

`reports/d1-ai-defaults.json` records 169→171 lifetime calls, $17.428208→$17.645884: **$0.217676** new spend. Remaining Night 3 allowance: **$9.251201**. Tests use scripted providers or local wire fixtures, not paid requests.

`reports/d1-start-state.json` and `d1-final-state.json` retain the source checksum: **1,233,000 rows, 6,523,011 requested units, 6,484,384 shipped units**. All **75 initial order quantities / 2,195 cases** are unchanged. The same-capacity replay still measures 11,160 vs 11,564 short units, 89 vs 75 shortage product-days and HK$68,203.72 vs HK$61,438.78 lost margin. Neither policy was adjusted. A 3.28 MB planning-state backup is retained under ignored `.codex/backups/day16-before.json`.

The replay cache version changed only for the revised event format. Central review also made widget Undo restore the layout ownership marker, so undoing a layout edit does not leave a false customisation behind. The app is left at the clean Report step after Reset, with the authored report and five widgets saved.
