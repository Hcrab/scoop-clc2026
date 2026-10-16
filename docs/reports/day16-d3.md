# Day 16 — D3 evidence

Starting revision `f7c31ef`. The [protocol](day16-d3-protocol.md) was written before inspecting new coverage or replay outcomes. The two authorised changes are implemented; no threshold, prior, critical-ratio cost, capacity or rule buffer was tuned. The wider tuning handoff was read on entering D3, but its multi-seed search is outside this day's scope.

## Acceptance

- ✅ Protection-period calibration and before/after coverage table: `reports/d3-coverage.json`, 478 individual windows in `d3-coverage-windows.csv`, diagnostic counts in `d3-coverage-diagnosis.json`. Evaluation uses the same forecasts and actuals for both methods, weekly origins 1 June–13 July, complete outcomes through 26 July. Every origin calibrates only on earlier complete forward outcomes. The empirical coverage target is **not fully achieved**; this is recorded below rather than described as guaranteed service.
- ✅ Illustrative heat timing: same nine temperatures and duration, shifted exactly one day to **30 July–7 August**, beginning three days after the Monday plan. `reports/d3-heat.json` proves the old generated baseline matched the live source before updating it, and the new generated source matches afterward. Pre-30-July requests, shipments, inventory, inherited POs, earlier weather/other forecast targets and the 66-pallet capacity retain their before hashes (`d3-before.json`, `d3-final-state.json`). Coupled requests preserve stochastic draws and use the existing temperature response, with no new randomness; future source shipments and stock are resimulated consistently. Only August's model needed retraining because its training inputs changed; earlier models and expectations before 30 July are unchanged (`d3-derived.json`).
- ✅ One measured default-week replay after both fixes: `reports/d3-replay.json.gz`, summary and stock-flow diagnosis in `d3-results.json`. Normal automatic economic critical ratios, `service_level=null`, Simple rule buffer 1.25, the same 66-pallet cold store. All three outcomes are reported below. Approval used the saved recalculated cases and did not alter them.
- ✅ Focused regression tests: **107 passed**, `reports/d3-accepted-tests-tests.txt`. They cover finite ranks, future poison labels, complete stores/days, calendar wait, monthly forward-model selection, actual planning integration, unchanged uncertainty quadrature/MOQs, deterministic heat coupling, other seeds, world/reset and replay behavior. Runtime world changes clear recent calibration scores; replay cache version is `same-cold-store-play-v9-conformal-heat`.

## Coverage on the fixed historical windows

| Measure | Nominal | Before | After |
|---|---:|---:|---:|
| Central demand interval coverage | 80% | 55.44% | 71.76% |
| One-sided upper demand coverage | 96.8% | 96.44% | 93.51% |
| Mean central interval width, units | — | 301.76 | 268.52 |
| Complete SKU/origin windows | — | 478 | 478 |

These are protection forecasts before cohort factors and case rounding, not measured fulfilment rates. The older 64.49% benchmark used a different world and 780 windows and is not this table's baseline. The recent calibration improves central coverage but **does not make a 96.8% target deliver 96.8% empirical upper coverage**. Of 31 upper misses, 26 occur at the 29 June and 6 July origins; the forecast/actual distributions shift while fully matured calibration errors lag. On 6 July the median actual/forecast ratio is 1.047 and the upper multiplier is 1.093; 15 products exceed that upper bound. Pooled, overlapping forward windows and changing models/weather/preferences are not exchangeable. No extra window selection, safety buffer or service adjustment was applied after seeing this table. The remaining calibration gap is a limitation of this fixed method.

The current 27 July plan uses 403 fully observed scores, with outcome cutoff 26 July; its ratio quantiles are 0.9003 / 0.9866 / 1.0753 at p10/p50/p90 and 1.1383 at p96.8 (`d3-orders.json`). Existing `[0.3, 3]` clipping and factor uncertainty remain in place. This is rolling normalized forward split calibration with finite ranks, not a claim that the daily LightGBM quantile regressors themselves now have exact coverage.

## Default-week outcomes, 27 July–11 August

| Whole warehouse | Before Scoop | Before Simple rule | After Scoop | After Simple rule |
|---|---:|---:|---:|---:|
| Units short | 11,160 | 11,564 | **7,570** | 12,151 |
| Stockout product-days | 89 | 75 | **62** | 79 |
| Lost margin, HK$ | 68,203.72 | 61,438.78 | **43,279.06** | 65,343.80 |
| Average closing pallets | 36.8642 | 36.6094 | 37.4736 | 35.9607 |
| Physical peak pallets | 57.9866 | 57.9866 | 57.9866 | 57.9866 |
| Days over capacity | 0 | 0 | 0 | 0 |

After both fixes, Scoop avoids **4,581 short units, 17 stockout product-days and HK$22,064.74 lost margin** versus the rule, using **1.5129 more average pallets**. Both peaks are 57.9866/66. Week-one cases rose from 2,195 to 2,532; none were cut for capacity. Cohort factors are exactly unchanged. Both policies serve identical requests within each comparison; requests differ between before and after because the heat timing changed. This joint experiment does not isolate the separate contribution of calibration or establish a multi-seed policy win.

## Report and final state

The saved report's old 132-case / HK$16,114 action claim no longer matched the revised card. Six local evidence queries were refreshed, then Gemini authored a grounded replacement, including its ordinary one-repair allowance: **2 calls, $0.237166**, model `gemini-3.8-flash` (`reports/d3-report-refresh.json`). Its two authored follow-ups remain under a sentence-case, normal-colour `Merchandising & planning checks` heading; no extra provider call or invented text was used (`d3-report-heading.json`). The initial Reset template contains the new orders and report; the app is back at the clean Report step.

Final source: 1,233,000 rows, 6,524,261 requested and 6,485,861 shipped units; the changed rows are future scenario facts. Provider ledger: **173 lifetime calls / $17.883050**, **$9.014035** left from the Night 3 allowance. `reports/d3-final-state.json` records these values and preserved history. The empirical coverage miss remains explicit despite the favourable illustrative Play result.
