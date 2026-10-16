# Default demo tuning and mid-course acceptance

The selected normal-code replay beats the unchanged Simple rule on all three Results measures. This phase changes cycle holding cost from 2.5% to 1% and shared usable capacity from 66 to 62 pallets. The existing 98% service ceiling, model/cohort settings, trends, revised heat and source history stay intact.

The current parameters are optimised for the demonstration scenario. Once real operational data is available, they will be re-optimised on that data.

## Chosen values and reasons

| Setting | Value | Business sentence |
|---|---:|---|
| Cycle cost of one excess unit | 1% × unit cost | Charge storage and financing while frozen stock remains saleable, without repeatedly charging a season-end markdown provision each cycle. |
| Usable positions, both policies | 62 pallets | The unchanged rule physically peaks at 93.53% of these positions, while the initial approved plan fits. |
| Service quantile ceiling | 98%, retained | Bound tail protection so a small chance of shortage does not consume arbitrarily much scarce space. |

No per-SKU case fixes are used. The initial plan has 2,413 cases, a 61.3045565-pallet peak and no cuts. The first card remains Strawberry → Value price → Water-based (IC006/061/062/063), +38.1552%, with +134 cases compared with the no-cohort plan. Its saved selected-versus-parent-rest drilldown is unchanged. The issued-weather model sees the whole 30 Jul–2 Aug heat episode. Dated allocation later cuts 552, 1,069 and 561 cases on 5–7 Aug, with expected peaks 61.9943, 61.9880 and 61.9962 pallets. These show actual information/space mechanisms; they do not isolate each component's causal share of the total gain.

## Before and after

27 Jul–11 Aug, 16 days, automatic margin objective, no overrides. Before is D4 at `e3597ef`; now is one ordinary API approval/replay, identical to the selected isolated trial.

| Measure | Scoop before | Scoop now | Simple rule, both | Current Simple minus Scoop |
|---|---:|---:|---:|---:|
| Units short | 6,347 | 4,297 | 6,063 | **1,766** |
| Stockout product-days | 52 | 36 | 39 | **3** |
| Lost margin, HK$ | 38,125.69 | 24,271.33 | 30,849.11 | **6,577.78** |
| Average closing pallets | 37.974486 | 38.620401 | 37.755089 | −0.865313 |
| Physical peak pallets | 57.986597 | 57.986597 | 57.986597 | 0 |
| Ending stock, units | 70,564 | 71,592 | 52,004 | −19,588 |
| Ordered cases across horizon | 8,352 | 8,066 | 7,917 | −149 |

Service improves with 0.865313 additional average pallets and more closing stock than the rule. Lost margin is gross margin on unmet requests; these outcomes do not measure net profit after storage/markdown. Neither policy exceeds capacity or defers receipts. Results rounds the exact HK$6,577.78 to **HK$6,578**.

Normal order hash: `a8ca053adf930b016e76346af923c992c3585c2df74e83b1f31ab5cfcc65e322`. Logic: `same-cold-store-play-v11-demo-carry-cost`. [Walkthrough](demo-walkthrough.json), [full replay](demo-replay.json.gz), [cross-artifact audit](demo-final-audit.json), [initial orders](demo-orders.json).

## Candidate record

Trials use normal recomputation and later automatic orders in an isolated schema without an answer-key table. Baseline first reproduced D4 exactly. Every rule summary stays **6,063 / 39 / HK$30,849.11**. Full quantities/projections/decisions: [selection](demo-selection.json), [original JSONL](demo-candidates.jsonl).

| Trial | Cycle cost | Max target | Capacity | Scoop units / days / HK$ loss | Disposition |
|---|---:|---:|---:|---|---|
| current | 2.5% | 98% | 66 | 6,347 / 52 / 38,125.69 | Exact before reproduction |
| carry-1pct | 1% | 99% | 66 | 3,628 / 29 / 21,933.62 | All three win; more average stock, looser store |
| carry-halfpct | 0.5% | 99.5% | 66 | 5,821 / 45 / 40,874.23 | Reject: days and margin worsen |
| one-tight60 | 1% | 99% | 60 | 7,080 / 59 / 50,128.84 | Reject: inherited opening projection exceeds 60 |
| one-tight62 | 1% | 99% | 62 | 6,255 / 54 / 45,089.01 | Reject |
| **one-cap98-tight62** | **1%** | **98%** | **62** | **4,297 / 36 / 24,271.33** | **Selected: all three win, opening fits, ceiling retained** |
| three-quarter-tight62 | 0.75% | 99% | 62 | 7,006 / 56 / 53,913.93 | Reject |
| half-tight62-committed | 0.5% | 99.5% | 62 | 7,369 / 58 / 55,694.00 | Reject |

Two earlier trials (`half-tight62`, `half-tight60`) are **excluded**: their capacity UPDATE was uncommitted when the independent planning connection read it, so first orders used the previous capacity. The harness now commits capacity first and records the planner's value; the corrected 62-pallet retest is above. Raw evidence is retained and flagged in `demo-selection.json`; neither invalid trial informs selection. Public source data was untouched by the trials.

`backend/scoop/play.py`, including the 28-day +25% rule, matches `e3597ef` after newline normalisation. Request/weather/opening/pipeline fingerprint: `b0b624c6c0c11649e955a5bf58de2b5e8126cb5ec661fb905d9b6218af1913d3`. No answer-key references in the scoped operational audit. [Fairness audit](demo-fairness-audit.json).

## Mid-course A

Only the actual ordering upper target is calibrated, with nonnegative one-sided excess scores and finite rank. At the chosen **98%** target, the same frozen **478** past windows cover **463 → 470** outcomes (**96.86% → 98.33%**); `ceil(479 × .98) = 470`. Bounds never shrink, central p10/p50/p90 stay unchanged. At the original 96.8% reference, fitted coverage remains 96.44% → 97.07%. [Window rows](demo-upper-windows.csv), [summary](demo-upper-calibration.json). This is fitted historical coverage; the earlier strict rolling-origin 96.8% evaluation remains 96.44% before/after (`reports/d4-upper-coverage.json`).

Heat remains **30 Jul–2 Aug**, temperatures **33.6/33.4/33.8/33.6°C**, wholly inside the 26 Jul issued forecast. Paired-generation tests verify original intensity, all pre-30-Jul requests/shipments/stock/POs/forecast targets, and RNG state. This tuning makes no further heat or demand edits. Timing evidence remains in `reports/d4-heat.json`.

## Validation

- **72 backend tests:** `python -m pytest tests/test_n5_algorithms.py tests/test_protection_calibration.py tests/test_heat_timing.py tests/test_dashboard_health.py tests/test_day_dashboard_events.py tests/test_simulation_jobs.py tests/test_cohort_planning.py tests/test_play.py tests/test_play_comparison.py -q`, from `backend`, fresh workspace-local `--basetemp`. [Output](final-tests.txt).
- **35 frontend tests:** `node --test frontend/tests/dashboard-health.test.cjs frontend/tests/operational-widget.test.cjs frontend/tests/play-clock-feed.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/widget-today.test.cjs`. [Output](final-frontend.txt). The final all-caps-title normalisation has this final unit/build verification; the six captured widget titles are unchanged by it.
- **Build:** `pnpm --dir frontend build`, TypeScript/Vite pass. [Output](final-build.txt). Existing 500 KB chunk warning remains.
- **Browser:** `pnpm --dir frontend exec playwright test walkthrough.spec.ts --reporter=line` against port 8009, Edge, **1 passed (2.0 min)**. No mocks or reused physical replay. Adding a widget triggers no replay request/hash/completion change; exact Undo and Reset restore five widgets and 2,413 cases. [Output](final-browser.txt).
- **UI grep:** expanded Watch/midnight/noon text has zero Recorded / Simulated / Requested / rule / Decision matches. [Command and scope](demo-ui-grep.json). This does not filter natural AI prose. Results retains the scenario/benchmark sentences under the latest instruction.
- **Gemini 3.8 Flash:** old quantity claims failed grounding, requiring a fresh report with the normal one-repair allowance. Two calls cost US$0.210555. Model HTML has no SVG; host data renders charts. [Record](demo-report-refresh.json).

## Visual review

All seven captures were opened and personally checked. Q1: purpose/next action within three seconds. Q2: one focal group. Q3: unnecessary/repeated copy. Q4: reachable provenance. Q5: presentation readability.

| Capture | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| [Report](../../docs/screenshots/demo-01-report.png) | Review orders clear. | Strawberry beside direction. | Concrete title, no slogan. | Evidence charts/controls. | 2,413 cases / 61.3 of 62 clear. |
| [Compound path](../../docs/screenshots/demo-strawberry-drilldown.png) | How we found it clear. | Selected compound branch. | Remainders add information. | Selecting a row changes curve. | +11.2/+23.6/+39.2% legible. |
| [Orders](../../docs/screenshots/demo-02-orders.png) | Export/Approve clear. | First cohort expanded. | No repeated introduction. | Product order evidence. | Stable columns, fitting capacity bar. |
| [Watch](../../docs/screenshots/demo-03-watch.png) | Up to the order; Next: Play. | Health then widgets. | No repeated subtitles. | Sources/low-cover list. | Grey metric, marker, short titles. |
| [00:50](../../docs/screenshots/demo-04-midnight.png) | Exact timestamp/Day 3. | Since-order health/events. | No extra status/rule caption. | Sources available. | No premature daily point. |
| [12:30](../../docs/screenshots/demo-05-noon.png) | Exact timestamp/Resume. | Six hollow projections. | Coffee has no Decision label. | Projected rows identified. | Separate hollow markers clear. |
| [Results](../../docs/screenshots/demo-06-results.png) | Three gains lead. | Shared stock comparison. | Context appears once. | Full comparison/sources. | Grey/green/orange, no bands/overlays. |

Final API state: clean Report, 75 lines / 2,413 cases, complete report, five widgets, no prepared replay after Reset. [State](demo-final-state.json). [Current acceptance ledger](../../docs/overnight-report.md) links the archived adverse D4 measurement and earlier phases.
