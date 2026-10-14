# Overnight delivery report — 14 October 2026

## Authoritative scope

The user's final handoff (`pasted-text-1.txt`, attachment 6b5dc399-bd07-404a-8507-28b5bc224e19) supersedes earlier product conventions where they conflict. Work proceeds P0 through P8 in order. No threshold tuning, new worlds, deployment, or history rewrite.

## P0 — Merge Play (complete)

- Merged `origin/claude/play-week-mvp` at `37146ae` into `claude/scoop-prototype`; Git reported no conflicts. Merge and regression tests are committed together after the green full test run.
- Frontend TypeScript and Vite build passes (39 modules).
- Conservation and shared-input regression tests pass. Full backend suite: 139 passed (one existing Starlette/AnyIO deprecation warning). Live seed-93 backend simulation passes. Edge browser verification at port 8009 ran Play to Day 7 of 7 (2 Aug), displayed Replay and the complete comparison table, and matched backend outcomes.

## Remaining phases

P1 null-world acceptance failed (12/17 weeks unsplit, 70.6% versus required 95%). P2 contextual overrides and uncertainty propagation, P3 agent tools and grounding, P4 unified pages/dashboard/Play, P5 typography and copy cleanup, P6 demo week selection, P7 documentation and clean-clone setup, P8 browser walkthrough and screenshot delivery are not yet implemented or verified.

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
- P2 uncertainty propagation, overrides and enriched cards remain unimplemented.

### P1 unresolved acceptance and next phase

P1 is not complete. The specified max-gain paired-permutation procedure fails the requested null-world rate with actual model residuals, despite passing the simplified independent-noise test. The evaluation uses the same seed-93 catalog and null-trained monthly forecasts, not a planted-world forecast. Potential causes such as dependence among district observations or forecast residual structure have not been established; no claim of statistical validity follows from this run. The handoff prohibits threshold tuning and directs blocked phases to be documented before proceeding. Continue P2 while preserving this unresolved requirement.
