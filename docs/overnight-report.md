# Day task — 16 October 2026

## Summary

Branch `claude/scoop-prototype`, starting revision `a9786c42c022029d4cd490a35b9f65472ad6d8c5`. Work proceeds D1→D4; every phase must pass its acceptance checks before the next starts, and is pushed when accepted. Night 3 is archived in [reports/night3.md](reports/night3.md).

| Phase | Status | Evidence |
|---|---|---|
| D1 Watch / Play dashboard | Accepted · `03fa6c9` | 81 backend + 12 frontend tests; real browser flow; four reviewed captures. [Evidence](reports/day16-d1.md). |
| D2 Small UI fixes | Accepted · `f7c31ef` | 12 backend + 18 frontend tests; real browser flow; both required captures reviewed. [Evidence](reports/day16-d2.md). |
| D3 Calibration and illustrative heat | Accepted; coverage target missed | 107 tests; fixed coverage table; one default replay. 7,570 vs 12,151 short units, 62 vs 79 product-days, HK$43,279.06 vs HK$65,343.80 lost margin. [Evidence](reports/day16-d3.md). |
| D4 Walkthrough and docs | Pending | Starts after D3 acceptance. |

Use only the remaining Night 3 Gemini allowance, and only if the report must be regenerated. Ordinary tests use the scripted provider. After D3: **173 lifetime calls / $17.883050**, with **$9.014035** left. The revised purchasing implications required a report refresh ($0.237166). Pre-heat history, opening stock, inherited orders and 66-pallet capacity are unchanged; the current plan has 75 lines / 2,532 cases. D3 improves this illustrative Play result on all three measures, but central 80% coverage remains 71.76% and the 96.8% upper target covers 93.51%. No extra tuning was applied. Reread the ledger before further paid generation.

## D1 — Watch / Play dashboard

- ✅ Watch — `docs/screenshots/d1-watch.png`, personally reviewed: four fixed tiles (99.1% fill, 11 products / 23 product-days, 38 low-cover products, 41.8 / 66 pallets) above five AI-selected detailed widgets. No loading overlay remains.
- ✅ Midnight — `docs/screenshots/d1-midnight.png`, personally reviewed: **29 Jul 00:50**, keys **7.1 days / 100% yesterday / 1,281 units yesterday / 2.5 days / 51.8 pallets**. No current-day partial chart point. Real browser **1 passed (1.7 min)**, `reports/d1-browser.txt/json`.
- ✅ Stock state — `docs/screenshots/d1-stock-state.png`, personally reviewed: light safe zone, amber below-cover segments and eight coral stockout dots. `d1-noon.png` verifies five separate hollow points after 12:00, with no connection to the completed series.
- ✅ UI grep — `reports/d1-static-checks.txt`: removed names/pending wording have zero matches in `frontend/src`; simple-rule orange occurs only in its palette declaration and Results chart. Browser also verifies no rule label or orange policy stroke in Play.
- ✅ Thresholds and list — **81 backend tests** in `reports/d1-final-backend-tests.txt` and **12 frontend tests** in `d1-final-frontend-python.txt`. Exact .95/.98 fill, 0/1/3/4 counts and .95/1 capacity boundaries; strict cover < lead; zero/null demand; historical cutoff; scoped list; empty layouts; no baseline access; 12:00 points; widget edit/Undo and initial snapshots are covered. Real browser opens the complete 38-product list and checks its first entry.
- ✅ Full behaviour — Five authored default widgets (`reports/d1-ai-defaults.json`); native add/edit/remove/chat and exact Undo tests pass; tiles are independent of editable widgets; numeric yesterday fallback and noon points pass; order events group by timestamp and expand to their product/cases/arrival/decision details. Arrival, shortage and heat events stay separate and use Scoop only. Production build passes (`d1-final-build.txt`). Both replay summaries exactly match Night 3: 11,160 vs 11,564 short units, 89 vs 75 product-days, HK$68,203.72 vs HK$61,438.78 lost margin. No model or policy changes. [Detailed record](reports/day16-d1.md).

## D2 — Small UI fixes

- ✅ Report heading — `Merchandising & planning checks`, computed colour `rgb(27, 56, 43)`, `text-transform: none`. Screenshot `docs/screenshots/d2-report-checks.png`, personally reviewed. Existing AI-authored questions are displayed under this normal heading; future report guidance uses sentence case. No new provider calls (`reports/d2-report-heading.json`).
- ✅ Results — Real browser **1 passed (1.5 min)** (`reports/d2-browser.txt/json`); screenshot `docs/screenshots/d2-results.png`, personally reviewed. One shared stock axis: 28 recorded grey dates through 26 July, green Scoop and orange Simple rule from the same 63,335-unit opening anchor. Three outcome numbers and See full comparison remain. Detailed policy widgets compare both runs only in Results; demand stays blue. **12 backend + 18 frontend tests**, production build pass (`d2-history-tests.txt`, `d2-frontend-python.txt`, `d2-build.txt`). All outcomes remain 11,160 vs 11,564 short units, 89 vs 75 product-days and HK$68,203.72 vs HK$61,438.78 lost margin. [Detailed record](reports/day16-d2.md).

## D3 — Calibration and illustrative heat

- ✅ Recent forward normalized split calibration implemented and evaluated on 478 fixed, temporally held-out windows (`reports/d3-coverage.json`, `d3-coverage-windows.csv`). Central 80% coverage: **55.44% → 71.76%**; nominal 96.8% upper coverage: **96.44% → 93.51%**. The upper target remains unmet and is diagnosed explicitly; no retuning. **107 tests passed** (`d3-accepted-tests-tests.txt`).
- ✅ Heat starts **30 July**, three days after the 27 July plan, and ends 7 August. Same nine temperatures, ordinary forecast errors and deterministic demand coupling; opening/history/PO/capacity hashes match before (`d3-heat.json`, `d3-before.json`, `d3-final-state.json`). Only future artifacts affected by changed source were rebuilt (`d3-derived.json`).
- ✅ One default replay, same 66 pallets and normal policies (`d3-replay.json.gz`, `d3-results.json`): all three before/after outcomes in [the table](reports/day16-d3.md). New Scoop / Simple rule: **7,570 / 12,151** short units, **62 / 79** product-days, **HK$43,279.06 / HK$65,343.80** lost margin. Both peak at 57.9866 pallets; Scoop uses 1.5129 extra average pallets. No other tuning. Grounded report and initial Reset template refreshed; app restored to Report.

## D4 — Walkthrough and docs

- ❌ Pending — Five-step walkthrough passes and screenshots are refreshed.
- ❌ Pending — TECHNICAL_DESIGN covers KPI tiles, colours, interval calibration and scenario change.
- ❌ Pending — Summary and every D1–D4 acceptance check have final evidence.
