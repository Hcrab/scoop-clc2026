# Overnight delivery report — 14 October 2026

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
