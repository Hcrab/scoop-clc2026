# Overnight delivery report — 14 October 2026

## Current acceptance ledger — strict sequential gates

The user's latest acceptance checklist supersedes the earlier permission to move on whenever a phase blocks. A phase now advances only after all checks pass, except a failure that can only be corrected by forbidden tuning, recorded as **❌ BLOCKED** with evidence. The authorized SKU-block/district-within-SKU permutation correction is being evaluated first. The authorized world-capacity correction is reserved for P6. The newly attached tuning-phase handoff has not been read; it is for after feature freeze.

Unaccepted P3/P4 code already written before this rule remains in the working tree; further implementation and acceptance of those phases is suspended while P1 is open. Earlier checkpoint statements below are historical evidence, not acceptance of these new gates.

### P1 — Cohort model: BLOCKED under the no-tuning exception, not accepted
- ❌ BLOCKED — Seed93/default week isolates planted strawberry SKUs after correction: **failed**. `scripts/evaluate-cohort-planted.py`, production `cohort_model.fit`, model `M202607-v1-s93`, week2026-07-27: all four targets remain in the 25-SKU water-based leaf. The water-based child selects `flavour:strawberry` as its best candidate (gain116.911817,17candidates), but corrected max-stat block-permutation p=0.1005025126 does not pass fixed alpha0.05. Full trace: `reports/cohort-seed93-block-evaluation.json`. Increasing alpha to admit this split would be forbidden tuning; no alpha, variance, prior, depth or data changes have been made.
- ❌ BLOCKED — Two null seeds/34 weeks: **4 root splits / 34**, exceeding maximum3. Seed93:4/17; seed42:0/17. `scripts/evaluate-cohort-null.py` completed all fixed Mondays11May–31Aug through production current-model rescoring. Full command and all34 rows: `reports/cohort-null-block-evaluation.json`. No threshold, prior, buffer or forecast hyperparameter was changed.
- ✅ Partial alignment and shrinkage tests: `test_partial_alignment_unaffected_sku_stays_near_control`, `test_halved_volume_moves_toward_leaf`; command `.venv/Scripts/python.exe -m pytest backend/tests/test_cohort_model.py -q --basetemp=../scoop-runtime/pytest-p1-paired-routing` → **11 passed in1.88s**. New tests verify intact district vectors, within-SKU district exchanges, incomplete-vector support, and `test_tree_uses_candidate_specific_permutations_with_paired_variances` verifies the actual tree routes each candidate to the proper paired `(y,v)` permutation.
- ✅ Per-planted-SKU table: `scripts/evaluate-cohort-planted.py` → `reports/cohort-seed93-block-evaluation.json`, production read-only fit after the permutation correction; table below. No fitting changes made to improve the result.

| Planted SKU | True injected recent multiplier | Raw recent requested/expected | Raw y | Fitted f50 |
|---|---:|---:|---:|---:|
| IC006 | 1.8000 | 2.237559 | 0.712237 | 1.808376 |
| IC061 | 1.8000 | 2.316007 | 0.753260 | 1.880651 |
| IC062 | 1.8000 | 2.197876 | 0.706093 | 1.834632 |
| IC063 | 1.8000 | 2.324204 | 0.712209 | 1.772804 |

True multiplier is the injected strawberry effect for13–26July, not a claim that all other world effects equal1. Raw ratio restores winsorised recent observations; raw y is the expected-recent-weighted mean of the four district log changes before shrinkage, retaining the specified promotion exclusion and winsorisation. District rows are in the JSON. The baseline includes the intervention ramp7–12July; no baseline modification has been made.

Evaluation-path audit: a read-only Python comparison constructed `build_features(make_world(93).static, pd.date_range('2026-05-18','2026-07-26'))` and the same features from `Static.load()`, sorted both by date/store/SKU, and ran `pd.testing.assert_frame_equal` on date and `FEATURES`. Output: **PASS: 105000 production and seed-local null feature rows match exactly, including all 22 model features and categorical levels.** All40 generated candidate groups also match the database groups. The null evaluator calls production `DemandModel.train`, `build_features`, `predict(mean_only=True)` and `fit_observations`, using each null seed's own catalog, demand, weather and promotions; it does not mix seeds or use planted forecasts.

Null-root diagnostics (all four splits are seed93; temperature in °C):

| Week | Split tag | p | Recent14 mean tmax | Baseline56 mean tmax | Retrain dates in70days | Retrain in recent14? |
|---|---|---:|---:|---:|---|---|
| 2026-05-11 | band:dairy:2 | 0.025126 | 24.9143 | 22.1625 | Apr1,May1 | Yes,May1 |
| 2026-06-15 | band:dairy:1 | 0.040201 | 27.4500 | 25.4536 | May1,Jun1 | Yes,Jun1 |
| 2026-07-27 | band:dairy:0 | 0.030151 | 30.6929 | 28.0375 | Jun1,Jul1 | No |
| 2026-08-24 | format:stick | 0.030151 | 29.2357 | 29.3411 | Jul1,Aug1 | No |

P1 exception decision: the authorized permutation correction and data-path audit are complete; the implemented fixed recipe produces these failures. Admitting the strawberry split requires changing the fixed significance rule or model inputs; suppressing the observed null splits by changing alpha or variance calibration would be tuning. No such changes are authorized tonight, and no further implementation discrepancy was found in this audit. Therefore these two measured checks remain **❌ BLOCKED**, not green. Advance to P2 under the user's explicit no-tuning exception. The weather/retrain diagnostics do not establish a cause of the false splits; no causal claim is made.

### P2 — Context and uncertainty: NOT YET ACCEPTED
- ❌ All five overrides change orders as specified: existing tests need phase acceptance verification after P1.
- ❌ Browser cards show cases/value/pallets/peak capacity: complete current screenshot evidence pending.
- ❌ Card override recomputes with before/after chip, exact order Undo: earlier real date-control verification exists, but new gate requires recorded exact-order and screenshot evidence after the P1 correction.
- ❌ Global stockouts/space control changes service level and orders: actual browser verification pending.

### P3 — Agent: NOT YET ACCEPTED
- ❌ New tool set exists and old direction/classification tools removed: implementation present but final integrated acceptance inspection pending.
- ❌ Exact strawberry utterance with Gemini, diff/recompute/Undo in browser: pending.
- ❌ Value-price−10% and peak≤90% via bulk edit, diff/Undo: focused backend tests exist; integrated browser evidence pending.
- ❌ Wrong report number rejected, repaired once, then fallback: grounding tests exist; full gate audit pending.
- ❌ No model SVG path and chart rendered from evidence: renderer test/screenshot exists (`docs/screenshots/report-chart-renderer-fixture.png`), remaining path audit pending.
- ❌ Empty GEMINI_API_KEY gives card-list report and all three scripted commands: integrated offline check pending.

### P4 — Pages: NOT YET ACCEPTED
- ❌ Cohort-first/family action list, expand,20rows,page edits,sticky live capacity: implementation in working tree; browser verification pending.
- ❌ Shared server widgets,+sheet,drag/remove,chat creation,extension during Play: implementation in working tree; integration and browser verification pending.
- ❌ Automatic Play horizon,affected summaries,two-line/dot charts,decision events,three results,week2line: implementation in working tree; integrated acceptance pending.
- ❌ Full browser flow report→card→override→orders→widget→Play→result: pending.

### P5 — UI: NOT YET STARTED UNDER NEW GATE
- ❌ No font-size outside type tokens: scan/fix/output pending.
- ❌ No banned strings: scan/fix/output pending.
- ❌ Screenshot per screen with answers to all five litmus questions: pending.

### P6 — Demo: NOT YET STARTED UNDER NEW GATE
- ❌ Seed93 only in UI/default: pending.
- ❌ Authorized capacity fix; history-rule peak90–95%: pending measurement and correction, no arbitrary lead-time edits.
- ❌ Default week selected from13/20/27July with reason: pending.
- ❌ Quiet week has no cohort cards: pending.
- ❌ Strawberry arrival within days2–5 reported without forcing: pending.
- ❌ Re-run Play policy lost-units/pallets beside P0 values1,815vs1,344: pending, report as measured.

### P7 — Docs: NOT YET STARTED UNDER NEW GATE
- ❌ Clean-clone README commands/output: pending.
- ❌ Technical architecture/algorithm sections/Simplifications/Limitations/disclosure: update and audit pending.
- ❌ App starts and works with empty GEMINI_API_KEY: pending.

### P8 — Walkthrough: NOT YET STARTED UNDER NEW GATE
- ❌ `frontend/e2e/walkthrough.spec.ts` passes end to end: pending.
- ❌ Every step screenshot in `docs/screenshots/`: only renderer fixture exists so far, not full walkthrough.
- ❌ Complete acceptance ledger and overnight report: current ledger explicitly records incomplete checks; final evidence pending.

## Authoritative scope

The user's final handoff (`pasted-text-1.txt`, attachment 6b5dc399-bd07-404a-8507-28b5bc224e19) supersedes earlier product conventions where they conflict. Work proceeds P0 through P8 in order. No threshold tuning, new worlds, deployment, or history rewrite.

## P0 — Merge Play (complete)

- Merged `origin/claude/play-week-mvp` at `37146ae` into `claude/scoop-prototype`; Git reported no conflicts. Merge and regression tests are committed together after the green full test run.
- Frontend TypeScript and Vite build passes (39 modules).
- Conservation and shared-input regression tests pass. Full backend suite: 139 passed (one existing Starlette/AnyIO deprecation warning). Live seed-93 backend simulation passes. Edge browser verification at port 8009 ran Play to Day 7 of 7 (2 Aug), displayed Replay and the complete comparison table, and matched backend outcomes.

## Remaining phases

P1 null-world acceptance failed (12/17 weeks unsplit, 70.6% versus required 95%). P2 context controls and P3 report/tool work are implemented in part, with evidence below. P3 unified widget tools, P4 unified pages/dashboard/Play, P5 typography and copy cleanup, P6 demo week selection, P7 documentation and clean-clone setup, and P8 full browser walkthrough remain incomplete.

## Existing state and exclusions

The previously implemented Trend Explorer and hand-drawn report charts are not the requested final design; they must be replaced according to the final handoff. Earlier test/build results do not prove the new phases complete. Product illustrations are lowest priority after all phases.

### P0 verification evidence so far

- Added two deterministic simulation tests, including nonzero historical in-transit receipts, a shortage, different new orders, and daily/full-period per-SKU conservation. Focused run: 2 passed.
- Restored the stopped local PostgreSQL using the existing start-db script. The first full suite returned 134 passed, 1 failed, 4 errors: four errors were an inaccessible pytest temporary directory; one stale test fake returned product rows for a nutrition query. The fake now distinguishes the queried entity, and a rerun uses a dedicated workspace basetemp.
- Actual seed 93, plan P20260727, seven days: all SKU stock balances and demand identities pass for both policies. Plan lost 1,815 units versus rule 1,344; average pallets 53.1651 versus 55.2196; both peak at 68.5983 pallets. These are observed MVP results, not tuned. Browser Play verification subsequently passed.

- The in-app browser entry timed out. Recovery used the available Edge browser through the same browser automation tool; the actual Play UI completed successfully.

## P1 — Cohort model and planning integration (implemented, acceptance blocked)

- Added the specified paired-permutation tree (199 permutations, depth 3, minimum 3 distinct SKUs) and two-level DerSimonian–Laird shrinkage, with promotion exclusion and store/SKU winsorisation. Category band labels now live in JSON configuration.
- New plans, recomputation, confirmation capacity and Play automatic later-week orders use one cohort factor per SKU. Main planning no longer calls the overlapping direction multiplier or trend enumeration. Saved cohort evidence refreshes alongside orders. Old direction APIs are awaiting replacement in P3.
- Reviewed and corrected the method trace's shrinkage weight labels and removed an unrequested 28-day minimum after promotion exclusions. Added a Play regression for calendars with no Monday order day.
- Full backend suite: 150 passed, one existing deprecation warning. After the API evidence-refresh change, 13 related tests passed.
- Read-only seed 93 / 27 July fit: 300 units, 6 leaves. The path water-based AND strawberry AND not-high-price-per-100ml isolates exactly IC006, IC061, IC062 and IC063. Their factors are 1.9979, 2.0560, 1.9732 and 1.9783, below raw recent observed/expected ratios 2.1855, 2.2708, 2.1560 and 2.2696. Evidence: `reports/cohort-seed93-evaluation.json`.
- Read-only integrated order calculation: the four final case quantities are 42, 31, 101 and 54. Projected warehouse peak is 69.6741 pallets, including inherited stock/pipeline; this is not a claim that occupancy is below the 56-pallet physical limit.
- Synthetic null-unit test: 19/20 weeks remain unsplit. This is not a substitute for the requested actual null world. `scripts/evaluate-cohort-null.py` trains monthly forecasts against `null_orders(93)` and evaluates the same preparation/fitting path without altering the demo database; its result is 12/17 weeks unsplit (70.5882%), below the required 95%. Five root splits occur on 11 May, 29 June, 27 July, 10 August and 24 August. Full evidence: `reports/cohort-null-evaluation.json`. No parameters have been tuned.
- P2 work followed this checkpoint; see the subsequent section.

### P1 unresolved acceptance and next phase

P1 is not complete. The specified max-gain paired-permutation procedure fails the requested null-world rate with actual model residuals, despite passing the simplified independent-noise test. The evaluation uses the same seed-93 catalog and null-trained monthly forecasts, not a planted-world forecast. Potential causes such as dependence among district observations or forecast residual structure have not been established; no claim of statistical validity follows from this run. The handoff prohibits threshold tuning and directs blocked phases to be documented before proceeding. Continue P2 while preserving this unresolved requirement.

## P2 — Context and uncertainty (backend checkpoint, not complete)

- `cohort_model.fit` now rescored the historical window using the model active for the plan, retaining historical issued-weather features. Eight model tests include a retrain-absorption example returning the factor to 1. The P1 issued-model null evaluation remains an unresolved acceptance result, not overwritten by this change.
- Added persistent definitions in `settings.cohort_overrides`, identified by tag path, districts and rule type. They carry across weeks; optional expiry is supported. `POST /api/plans/{pid}/overrides` returns before/after snapshots and affected order rows and records the edit. Rules can be applied in Discover, Direction or Execute; Execute returns to Direction for a new decision.
- Implemented one-off, dated end, posterior cap, expectation prior and final-case overrides. End dates use the actual supplier order/arrival calendar and arithmetic cover-day weighting. Expectation priors combine with leaf data; no stored demand multipliers are reused.
- Replenishment combines factor log uncertainty with the empirical forecast-error distribution using deterministic 41-node Gaussian quadrature. Zero uncertainty preserves the previous calculation; the capacity-cut algorithm is unchanged. Direct case edits update the projected occupancy.
- `GET /api/plans/{pid}/cohorts` computes decision cards with tag definitions, per-SKU factors/cases, expected shortage-margin difference, pallet difference, peak occupancy, representative SKU and detailed evidence. The current frontend does not yet display these cards or override controls; P2's visible acceptance is therefore not complete.
- Read-only seed-93 evaluation is saved in `reports/cohort-overrides-evaluation.json`. One-off and an end before arrival yield factor 1 for all four target SKUs. A +30% cap produces factors 1.2852–1.2884. A direct IC006 override gives 5 cases without changing its factor. The target card reports +231 cases against unadjusted orders, 3.85 additional pallets and 35,950.22 expected shortage margin avoided. These are model calculations, not realized sales or guaranteed outcomes. Peak occupancy is 69.7548 pallets including inherited stock/pipeline, above physical capacity.
- Full backend suite: 167 passed (one existing deprecation warning). After final case-occupancy correction: 19 related tests passed, then four planning tests passed including the new direct-case occupancy regression (168 collected tests now).
- Approximation to document: capped units retain truncated marginal moments but omit their cross-district covariance; partial-duration uncertainty uses a delta-method transform. This does not establish exact joint-posterior calibration. Card presentation, full UI controls, Undo and the P3 agent replacement remain unfinished.

### Checkpoint delivery status

User-requested checkpoints were pushed at `14862b3` and `c998d62`; these are work-in-progress snapshots, not phase acceptance claims. P1's null acceptance remains unresolved. P3–P8 remain outstanding; no overall completion is claimed.

### P2/P3 subsequent implementation and verification

- Cohort cards and context controls now render alongside the report. In the actual seed-93 browser flow, an end date of 10 August changed the leading card from +231 to +158 cases; Undo restored +231 and the previous Execute stage. This verifies the direct control path, not the required live-agent utterance.
- Report charts now use application-rendered `Chart` data from evidence. The renderer test passed in Edge and saved `docs/screenshots/report-chart-renderer-fixture.png`. Its report is explicitly a fixture; it is not a regenerated Gemini report or the full P8 walkthrough.
- Report claim grounding checks cited numbers, percentage units and dates, with one repair round before offline fallback. Full method traces are retained in program evidence but omitted from the initial model context to keep the request manageable.
- Context, goal and batch quantity edits record snapshots and expose shared Undo receipts. Capacity fitting now starts the existing greedy cut from current case quantities, preserving manual quantities whenever the requested space limit already fits. Derived card/report refreshes no longer invalidate Undo; later business-state edits still do.
- Focused verification after these corrections: 9 bulk-order/context tests passed; TypeScript and Vite build passed. Full backend suite: 185 passed, one existing Starlette/AnyIO warning. The first run had four temporary-directory permission errors and one obsolete classification-flow assertion; using a dedicated runtime temp directory and replacing that assertion with the current no-classification behavior resolved them. Edge renderer test: 1 passed (17.6 seconds); screenshot inspected with chart, time controls and query visible.
- Remaining P3 work includes shared dashboard/widget tools and verifying the specified utterance in the actual chat. Remaining P4 work includes grouped editable orders, server-side dashboard layout, the complete consequence window and result presentation.

Earlier P2 checkpoint paragraphs describe the state at that checkpoint; the frontend and Undo limitations there have since been addressed as recorded above. The active seed-93 warehouse capacity is 68 pallets; the older reference to 56 pallets above is stale and must not be used to interpret current capacity results.
