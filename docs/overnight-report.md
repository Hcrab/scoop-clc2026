# Night 3 — acceptance and delivery

## Summary — 15–16 October 2026

| Phase | Status | Commit | Evidence / open issue |
|---|---|---|---|
| Requested pre-step: fast Reset | Accepted | `425ab1f` | Reset API 174 / 85 / 94 ms; usable report after 1.404 s; 47 focused backend tests and the real Settings flow pass. |
| M1 Same cold store | Accepted | `517d776` | 25 tests + real Results capture; both peaks 57.9866 / 60; 404 units avoided, 14 extra product-days, HK$6,764.94 extra lost margin. Five-SKU diagnosis and fixes recorded. |
| M2 Demo start state | Accepted | `b564792` | Capacity 66 pallets; projected peak 61.3046 = 92.8857%. Source requests, stock, policy settings and ledger retained. |
| M3 Report layout and language | Accepted | `f176128` | 76 tests + real preview/Apply/Undo/action-link/scroll flow; Gemini report regenerated; screenshots reviewed. |
| M4 Play widget values | Accepted | This phase | 27 backend + 4 frontend tests; real 00:50 capture shows 3 / 4 units and separate partial points; full-day close verified. |
| M5 Walkthrough and docs | Not started | — | Refresh the five-step captures and document the delivered comparison. |

Branch `claude/scoop-prototype`; starting revision `43b44fae4c70806137e276cfc4479ae5d955abee`. Night 2 is archived in [reports/night2.md](reports/night2.md). The user explicitly requested fast Reset before supplying the Night 3 handoff; finish and push it before M1. Work proceeds M1→M5 in order, with evidence for every check and a push after each accepted phase. No multi-seed work, deployment, slide deck, rebase or force-push.

Tonight's new Gemini allowance is **$10**, starting after **160 historical calls / $16.897085 estimated or reserved**. The full ledger is retained. The cumulative enforcement cap is **$26.897085**; a new 120-call allowance gives a cumulative call cap of 280. This does not grant $26.90 of new usage. Receipt: `reports/night3-budget-start.json`. Reuse the stored report until M3 is complete, then regenerate it with `gemini-3.8-flash`. Ordinary tests use the scripted provider.

After M3: **169 lifetime calls / $17.428208**, hence **$0.531123 new Night 3 usage**, approximately **$9.468877** of tonight's allowance remaining. The final regenerated report is persisted and included in the clean Reset template.

## Requested pre-step — fast Reset

- ✅ Backend behavior — **47 passed in 26.62 s** across `tests/test_demo_settings.py`, `test_cohort_planning.py`, `test_weekly_review.py` and `test_simulation_jobs.py`. Output: `reports/fast-reset-backend-tests.txt`. Tests cover exact initial rows/report/widget/topic restoration, repeat reset, reopened manager persistence, source/budget retention, atomic rollback, same-world selection, cold-week preparation and rejecting manual edits as a new baseline. Concurrency tests hold a background GET open while reset succeeds, and hold a real mutation open until it finishes before reset clears it.
- ✅ Browser — `pnpm --dir frontend exec playwright test fast-reset.spec.ts --reporter=line` against the real 8009 API → **1 passed (43.7 s)** for the full setup/edit/reset/reload test. The three reset requests took **174 / 85 / 94 ms**; the first confirmation click received its response in **221 ms**, and the usable Report returned in **1.404 s**. All **75 orders, five default widgets, cards and stored report** match the initial state; progression returns to Report and decisions/chat are cleared. Evidence: `reports/fast-reset-browser.json`, `fast-reset-browser-tests.txt`. No mocked responses or page errors.
- ✅ Source and allowance — Source remains **1,233,000 rows / 6,523,011 requested units / 6,484,384 shipped units**. No replay is queued and overrides are cleared. Provider ledger remains **160 calls / $16.897085**; this verification made **zero provider calls** and spent **$0** of the new Night 3 allowance. `reports/fast-reset-before.json`, `fast-reset-after.json`, `night3-budget-start.json`. Screenshot `docs/screenshots/fast-reset-report.png` was personally reviewed: original report and images are loaded, only Report is progressed, columns align and no loading state is retained. `git diff --check` passes.

Initial planning templates are keyed by seed and week in the existing Settings table. Same-world prepared resets restore only small planning records and clear manual context, decisions, chat, confirmations and progression; they do not snapshot source tables, invalidate model caches or call Gemini. The first authored report is captured from its active transaction only while the plan is untouched. A new week needs initial mechanical preparation once. Private world-switch snapshots remain available.

Central performance review found a second bottleneck after the rebuild was removed: the old full-world gate spent **10.421 s** waiting for a background read, versus **120 ms** restoring rows. Prepared same-world reset now waits only for actual mutations, so read-only summaries can finish without delaying it. Full source-world replacement still drains all work. Derived replay workers may finish but cannot resurrect a reset job; stored order hashes retain their stale-result checks. The initial template remains separate from mutable summary fields and always restores the Report step.

Local runtime repair: PostgreSQL accepted TCP but could not complete new sessions; its log recorded new-worker startup failures. The owned loopback cluster was restarted, retaining data files, with output redirected to its existing server log. Fresh `SELECT 1` then completed in about 0.1 s. No source data was regenerated. A one-time 1.28 MB planning backup is retained at ignored `.codex/backups/fast-reset-before.json`; source order rows were **1,233,000**, ordered units **6,523,011**, shipped units **6,484,384**.

## M1 — Same cold store, normal policies

- ✅ Shared capacity — **25 passed** (`reports/m1-tests.txt`); saturated receipts and pipeline conservation checked. Default daily/hourly/ten-minute peaks are **57.9865972222 / 60 pallets** for both, with zero over-capacity days (`reports/m1-diagnosis.json`). The queue executes one normal replay, with no service search.
- ✅ Results — Real browser test **1 passed (1.4 min)** (`reports/m1-browser.txt`, `m1-browser.json`); screenshot `docs/screenshots/m1-results.png` personally reviewed: three aligned numbers, adverse outcomes in red and one same-cold-store line. Production build passed (`reports/m1-build.txt`); saved orders unchanged.
- ✅ Diagnosis alternative — **404 fewer units short, 14 extra stockout product-days, HK$6,764.94 extra lost margin**. [Five-SKU diagnosis and fixes tried](reports/night3-m1.md) traces dated receipts and shortages. Zero first-week capacity cuts and no deferred receipts: the observed gap comes from lower normal coverage before later replenishment, not strawberry displacing those SKUs through space cuts. No threshold/buffer changes. Ledger unchanged at 160 calls / $16.897085.

## M2 — Demo start state

- ✅ Default start — **61.3045565055 / 66 = 92.885691675%**, within 90–95%. Changed only the seed-93 physical capacity from 60 to 66, both in generator configuration and the existing local world; the peak is unchanged and no forecast/policy threshold was tuned. `reports/m2-start-state.json`, command output `m2-world-python.txt`. Source remains 1,233,000 rows / 6,523,011 requested / 6,484,384 shipped; zero provider calls. Recomputed native orders/cards and refreshed the clean Reset template. The stored report is deliberately reused until M3 regeneration. Future over-capacity presentation is part of M3. The measurement script now checks projected start-state occupancy, retaining replay peaks as context.

## M3 — Report text and layout

- ✅ Screenshots — `docs/screenshots/m3-direction.png`, `m3-actions.png`, `m3-scrolled-left.png`, `m3-narrow-direction.png`, all personally inspected. Final real browser test **1 passed (35.4s)** (`reports/m3-browser.txt/json`): previews change cases without writes; Apply matches preview; Undo restores exact orders; linked actions highlight the card; desktop scrolls independently and narrow layout stacks. Final report uses one estimated-effect key and muted one-decimal context, with no capacity paragraph in its action list. [Details](reports/night3-m3.md).
- ✅ Magnitudes and integration — **63 + 13 = 76 tests passed**, `reports/m3-tests.txt`, `m3-grounding-tests.txt`; exact ±10/±30 boundaries covered in `test_cohort_cards.py`. Production build passes (`m3-build.txt`). Native words are algorithm output. No model/policy tuning.
- ✅ UI text — `reports/m3-ui-text-check.txt`: `rg -n -F` has no matches for any prohibited string, including both arrow variants. Gemini fresh report + one visual pass total **9 calls / $0.531123**. Final API and Reset presentation hashes agree (`m3-final-state.json`); source requests and ledger history retained.

## M4 — Play widget values

- ✅ Midnight and closing state — `night3-m4.spec.ts` against the real API: **1 passed (2.7 min)**. At **29 Jul 00:50**, cohort widgets show **3 / 4 units today so far**, warehouse stock **74,327**, and **51.8 pallets**. Screenshot `docs/screenshots/m4-midnight.png` personally reviewed: complete-day lines stop before independent hollow partial points. Full-day closing values agree with raw daily totals; saved orders unchanged; no page errors. `reports/m4-browser.txt/json`.
- ✅ Supporting checks — **27 backend + 4 frontend tests**, production build and `git diff --check` pass (`reports/m4-tests.txt`, `m4-frontend-python.txt`, `m4-build.txt`). Daily enrichment conservation and monotone cumulative shortage are tested. The illustrative clock adds 10% uniform background requests while keeping daily quantities and policy outcomes unchanged; no forecast/policy tuning or provider calls. [Details and the different-capacity comparison correction](reports/night3-m4.md).

## M5 — Walkthrough and documentation

- ❌ Pending — Five-step walkthrough passes, `docs/screenshots/n6-*.png` refreshed, TECHNICAL_DESIGN and Simplifications updated, summary covers every phase.
