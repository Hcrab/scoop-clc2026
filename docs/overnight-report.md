# Night 3 — acceptance and delivery

## Summary — 15–16 October 2026

| Phase | Status | Commit | Evidence / open issue |
|---|---|---|---|
| Requested pre-step: fast Reset | Accepted | `425ab1f` | Reset API 174 / 85 / 94 ms; usable report after 1.404 s; 47 focused backend tests and the real Settings flow pass. |
| M1 Same cold store | Not started | — | Remove matched-space bisection; capacity constraints and five-SKU loss diagnosis. |
| M2 Demo start state | Not started | — | Default projected peak at 90–95% of physical capacity. |
| M3 Report layout and language | Not started | — | Direction preview, action rows, native metrics and independent columns. |
| M4 Play widget values | Not started | — | Today-so-far values and partial daily curves without a midnight zero drop. |
| M5 Walkthrough and docs | Not started | — | Refresh the five-step captures and document the delivered comparison. |

Branch `claude/scoop-prototype`; starting revision `43b44fae4c70806137e276cfc4479ae5d955abee`. Night 2 is archived in [reports/night2.md](reports/night2.md). The user explicitly requested fast Reset before supplying the Night 3 handoff; finish and push it before M1. Work proceeds M1→M5 in order, with evidence for every check and a push after each accepted phase. No multi-seed work, deployment, slide deck, rebase or force-push.

Tonight's new Gemini allowance is **$10**, starting after **160 historical calls / $16.897085 estimated or reserved**. The full ledger is retained. The cumulative enforcement cap is **$26.897085**; a new 120-call allowance gives a cumulative call cap of 280. This does not grant $26.90 of new usage. Receipt: `reports/night3-budget-start.json`. Reuse the stored report until M3 is complete, then regenerate it with `gemini-3.8-flash`. Ordinary tests use the scripted provider.

## Requested pre-step — fast Reset

- ✅ Backend behavior — **47 passed in 26.62 s** across `tests/test_demo_settings.py`, `test_cohort_planning.py`, `test_weekly_review.py` and `test_simulation_jobs.py`. Output: `reports/fast-reset-backend-tests.txt`. Tests cover exact initial rows/report/widget/topic restoration, repeat reset, reopened manager persistence, source/budget retention, atomic rollback, same-world selection, cold-week preparation and rejecting manual edits as a new baseline. Concurrency tests hold a background GET open while reset succeeds, and hold a real mutation open until it finishes before reset clears it.
- ✅ Browser — `pnpm --dir frontend exec playwright test fast-reset.spec.ts --reporter=line` against the real 8009 API → **1 passed (43.7 s)** for the full setup/edit/reset/reload test. The three reset requests took **174 / 85 / 94 ms**; the first confirmation click received its response in **221 ms**, and the usable Report returned in **1.404 s**. All **75 orders, five default widgets, cards and stored report** match the initial state; progression returns to Report and decisions/chat are cleared. Evidence: `reports/fast-reset-browser.json`, `fast-reset-browser-tests.txt`. No mocked responses or page errors.
- ✅ Source and allowance — Source remains **1,233,000 rows / 6,523,011 requested units / 6,484,384 shipped units**. No replay is queued and overrides are cleared. Provider ledger remains **160 calls / $16.897085**; this verification made **zero provider calls** and spent **$0** of the new Night 3 allowance. `reports/fast-reset-before.json`, `fast-reset-after.json`, `night3-budget-start.json`. Screenshot `docs/screenshots/fast-reset-report.png` was personally reviewed: original report and images are loaded, only Report is progressed, columns align and no loading state is retained. `git diff --check` passes.

Initial planning templates are keyed by seed and week in the existing Settings table. Same-world prepared resets restore only small planning records and clear manual context, decisions, chat, confirmations and progression; they do not snapshot source tables, invalidate model caches or call Gemini. The first authored report is captured from its active transaction only while the plan is untouched. A new week needs initial mechanical preparation once. Private world-switch snapshots remain available.

Central performance review found a second bottleneck after the rebuild was removed: the old full-world gate spent **10.421 s** waiting for a background read, versus **120 ms** restoring rows. Prepared same-world reset now waits only for actual mutations, so read-only summaries can finish without delaying it. Full source-world replacement still drains all work. Derived replay workers may finish but cannot resurrect a reset job; stored order hashes retain their stale-result checks. The initial template remains separate from mutable summary fields and always restores the Report step.

Local runtime repair: PostgreSQL accepted TCP but could not complete new sessions; its log recorded new-worker startup failures. The owned loopback cluster was restarted, retaining data files, with output redirected to its existing server log. Fresh `SELECT 1` then completed in about 0.1 s. No source data was regenerated. A one-time 1.28 MB planning backup is retained at ignored `.codex/backups/fast-reset-before.json`; source order rows were **1,233,000**, ordered units **6,523,011**, shipped units **6,484,384**.

## M1 — Same cold store, normal policies

- ❌ Pending — Test both policies use the same physical capacity and neither exceeds it.
- ❌ Pending — Results screenshot shows the three outcomes and one same-cold-store line.
- ❌ Pending — All three outcomes improve, or five-SKU diagnosis and fixes tried are reported.

## M2 — Demo start state

- ❌ Pending — Default week's projected peak is 90–95% of capacity, with the measured number.

## M3 — Report text and layout

- ❌ Pending — Screenshots show the new direction/slider block, card language, left action summary and independently scrolled left column.
- ❌ Pending — Magnitude-word bands are tested: below 10% slightly, 10–30% moderately, above 30% sharply.
- ❌ Pending — Removed UI strings have no matches: Stock and space; Fewer stockouts ↔ Less space; Warehouse storage notice.

## M4 — Play widget values

- ❌ Pending — A midnight capture shows meaningful non-zero widget values and curves without a zero drop.

## M5 — Walkthrough and documentation

- ❌ Pending — Five-step walkthrough passes, `docs/screenshots/n6-*.png` refreshed, TECHNICAL_DESIGN and Simplifications updated, summary covers every phase.
