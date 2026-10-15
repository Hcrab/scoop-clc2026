# M1 — same cold store

Seed 93, week of 27 July 2026; replay 27 July–11 August. Both policies use the same 60-pallet cold store and identical requests, opening stock and inherited deliveries. Scoop uses the approved quantities and automatic critical ratios (`service_level=null`); the moving-average rule keeps its 1.25 buffer. The job calls the ordinary replay once. No service search or matched-space result remains.

| Whole warehouse | This plan | Moving-average rule |
|---|---:|---:|
| Units short | 11,160 | 11,564 |
| Stockout product-days | 89 | 75 |
| Lost margin, HKD | 68,203.72 | 61,438.78 |
| Average closing pallets | 36.5785 | 36.6094 |
| Physical peak pallets | 57.9866 | 57.9866 |
| Days above capacity | 0 | 0 |

The plan avoids 404 units short, but adds 14 stockout product-days and HK$6,764.94 lost margin. Results displays both losses in red. The three metrics measure different things: a small shortage of an expensive SKU can add one product-day and substantial margin while fewer low-price units are short overall.

## Five-SKU diagnosis

These five SKUs account for HK$9,459.83 of extra lost margin; improvements elsewhere offset HK$2,694.89 of that amount. None belongs to the selected strawberry leaf. Their first-week capacity cuts are all zero; no receipts are deferred in this replay. The strawberry allocation did not displace their orders through capacity cutting.

| SKU / product | First order, plan / rule (cases) | Extra units short | Extra product-days | Extra lost margin | Stock-flow evidence |
|---|---:|---:|---:|---:|---|
| IC010 Mango Sticky Rice Bar | 54 / 71 | 680 | 1 | HK$3,230.00 | 2,160 / 2,840 units arrive 4 Aug. Plan runs out 8 Aug; both run out 9 Aug. Next receipt is 11 Aug. |
| IC075 Strawberry Reserve Cream Bar | 18 / 24 | 201 | 2 | HK$1,766.79 | 720 / 960 arrive 5 Aug. Plan loses 77 and 124 units on 10–11 Aug while the rule retains stock. |
| IC014 Green Apple Sorbet Tub | 18 / 32 | 84 | 2 | HK$1,752.24 | 108 / 192 arrive 5 Aug. Plan runs out 9 Aug; the rule lasts until 11 Aug. Unit margin is HK$20.86. |
| IC045 Durian Cream Cup | 29 / 37 | 192 | 1 | HK$1,503.36 | 696 / 888 arrive 4 Aug. Plan runs out 9 Aug; next receipt is 11 Aug. |
| IC040 Mango Mochi 6-Pack | 25 / 31 | 72 | 1 | HK$1,207.44 | 300 / 372 arrive 4 Aug. Plan runs out 8 Aug; next receipt is 11 Aug. Unit margin is HK$16.77. |

The automatic targets give these products smaller first orders than the rule's 25% buffer. Their cohort multipliers are close to one (0.9776–1.0040). Larger automatic orders placed in week two arrive after the shortage window, so they cannot repair it retrospectively. This is a forecast/coverage and lead-time limitation in this illustrative path, rather than a physical-space shortage. Per-date demand, receipts, quantities, closing stock and losses for all 75 SKUs are retained in `reports/m1-diagnosis.json`; the complete replay is `reports/m1-replay.json`.

## Fixes applied and checked

1. Removed the matched-space/bisection runtime and service-level candidate repricing. The normal-policy measurements above retain the saved automatic settings and never modify approved quantities. The previous path had selected those same quantities in this world, so removing it does not itself change these losses.
2. Added one physical receiving constraint shared by both policies. If incoming units exceed available space, proportionally admitted whole units enter storage and the rest remain in pipeline for tomorrow. Tests saturate the cold store and verify inventory/pipeline conservation, stable rounding and daily/hourly/ten-minute capacity limits. Default receipts all fit, so this correction does not change its loss totals.
3. Checked whether capacity cuts or zero-cover allocation required a minimum-cover correction: the default has **zero cut cases across all 75 SKUs** and no deferred receipt. No minimum-cover floor, service threshold, forecasting parameter, rule buffer or scenario adjustment was applied in M1.

The daily model allows receiving part of a case as whole units; waiting inbound has no separate dock cost or capacity. This simplification applies equally to both policies. An impossible opening inventory above capacity raises an error instead of discarding stock.

## Acceptance evidence

- ✅ `pytest tests/test_play.py tests/test_play_comparison.py tests/test_intraday.py tests/test_simulation_jobs.py -q`: **25 passed**, output `reports/m1-tests.txt`. The queue test verifies one ordinary call; saturated fixtures verify shared capacity and conservation.
- ✅ Real browser approval → prepared replay → Results: **1 passed (1.4 min)**, `reports/m1-browser.txt` and `m1-browser.json`. Approved quantities remain unchanged; no browser errors. The result view was selected through flow endpoints after preparation; the complete timed replay is reserved for M5.
- ✅ Default-world daily, hourly and every ten-minute inventory inspected for both policies: peak **57.9865972222 ≤ 60**, zero negative inventory, zero over-capacity days. `reports/m1-diagnosis.json`.
- ✅ Screenshot `docs/screenshots/m1-results.png` personally inspected: three aligned outcomes, two clearly adverse outcomes, same-cold-store line directly beneath, whole-warehouse chart and normal-policy legends. No matching copy or second comparison table.
- ✅ Frontend production build, `reports/m1-build.txt`. Provider ledger remains **160 calls / $16.897085**; M1 uses **$0** of the new allowance.

M1 is accepted through the explicit diagnosis-and-fixes alternative. It does not claim superiority on all three metrics.
