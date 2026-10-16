# Day task — 16 October 2026

## Summary

Branch `claude/scoop-prototype`, starting revision `a9786c42c022029d4cd490a35b9f65472ad6d8c5`. Work proceeds D1→D4; every phase must pass its acceptance checks before the next starts, and is pushed when accepted. Night 3 is archived in [reports/night3.md](reports/night3.md).

| Phase | Status | Evidence |
|---|---|---|
| D1 Watch / Play dashboard | Accepted · `03fa6c9` | 81 backend + 12 frontend tests; real browser flow; four reviewed captures. [Evidence](reports/day16-d1.md). |
| D2 Small UI fixes | Accepted | 12 backend + 18 frontend tests; real browser flow; both required captures reviewed. [Evidence](reports/day16-d2.md). |
| D3 Calibration and illustrative heat | Pending | Two authorised changes; normal policies and the same 66-pallet cold store. |
| D4 Walkthrough and docs | Pending | Starts after D3 acceptance. |

Use only the remaining Night 3 Gemini allowance, and only if the report must be regenerated. Ordinary tests use the scripted provider. After D1: **171 lifetime calls / $17.645884**, including **$0.217676** for report authoring with the new AI widget selection. Night 3 plus today has used $0.748799 of its $10 allowance; **$9.251201 remains**. Source quantities, all 75 order lines and 2,195 cases are unchanged. Reread the ledger before any further paid generation.

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

- ❌ Pending — Split-conformal protection-period quantiles on recent forward errors: held-out interval coverage before/after table.
- ❌ Pending — Heat starts 3–6 days after the order date, inside this week's cover window and issued-forecast skill window; document both changes.
- ❌ Pending — One default-week replay, same cold store and normal policies: all three outcomes before/after; short diagnosis if not all three improve. No other tuning.

## D4 — Walkthrough and docs

- ❌ Pending — Five-step walkthrough passes and screenshots are refreshed.
- ❌ Pending — TECHNICAL_DESIGN covers KPI tiles, colours, interval calibration and scenario change.
- ❌ Pending — Summary and every D1–D4 acceptance check have final evidence.
