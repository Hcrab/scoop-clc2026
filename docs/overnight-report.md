# Night 2 — acceptance and delivery

## Summary — 15 October 2026

| Phase | Status | Commit | Main evidence / open issue |
|---|---|---|---|
| N1 Five-step flow | Accepted | `1a7b2ada3401` | Five screens; persisted replay; widget edits do not simulate. Cold preparation 37.203 s; accepted browser flow reused it. |
| N2 Hours and minutes | Accepted | Pending commit | 129,600 balances checked; 31 correctly timed shortages; 31.212 s replay versus 30.931 s expected. |
| N3 UI polish | Not started | — | Begins after N2 acceptance. |
| N4 Product illustrations | Not started | — | 75 individual illustrations and a reviewed contact sheet. |
| N5 Compound demo scenario | Not started | — | Single illustrative world; only the explicitly authorized small algorithm changes. |
| N6 Walkthrough and docs | Not started | — | Final five-step walkthrough and documentation. |

Starting revision: `e12d5977f85b8564618109f6eb4585eeaeed3d55`, branch `claude/scoop-prototype`. Night 1 is archived in [reports/night1.md](reports/night1.md). N1 is accepted and pushed as implementation 1a7b2ada3401 with ledger revision 2526180c1b5e; remote SHA verified. N2 is accepted; N3–N6 have not begun.

Key numbers at the start of this run: Gemini ledger **138 calls, $14.671322 estimated/reserved of the existing $20 total**; remaining **$5.328678**. The ledger and reservations are retained. Tests use the scripted provider unless a live call is specifically under review. Source world: seed 93, current date 20 July 2026, 75 products, plan `P20260720`, 5 widgets. User edits made after Night 1 are preserved; the ignored baseline snapshot is `.codex/backups/night2-baseline.json`.

Open acceptance questions: N3 evidence and report presentation; N4 consistency across 75 images; N5 whether the designed compound cohort is isolated and wins at matched average pallets. These are work to verify, not claims of completion.

## Rules and scope

The user's final Night 2 handoff controls this run. Work proceeds N1–N6 in order; record every check below as ✅ or ❌ with actual evidence, inspect changed-screen screenshots, and push each accepted phase before starting the next. Only an acceptance item requiring an explicitly forbidden action may be recorded as **❌ BLOCKED** and carried forward. No deployment, slide deck, multi-seed tuning, held-out evaluation, rebase or force-push. The new scenario is illustrative, not a proof of general superiority.

## N1 — Five-step flow

- ✅ Browser — `pnpm --dir frontend exec playwright test n1-flow.spec.ts --reporter=line` → **1 passed (1.5m)**. Real API and stored Gemini report; no mocked responses. Added, edited and reordered a widget with zero POST `/play` or `/simulation` requests. Play started automatically, Pause/Resume worked, the final frame retained Play until See results, and Results contained three numbers, the full comparison and final widgets. Screenshots: `docs/screenshots/n1-01-report.png` through `n1-05-results.png`. Raw evidence: `reports/n1-flow.json`.
- ✅ Timing — First cold run queued **17:23:03.831**, started **17:23:03.911**, completed **17:23:41.193** Asia/Shanghai (**37.203 s**). The accepted browser pass explicitly reused that ready persisted result; its Play-entry timestamp is **2026-10-15T09:40:06.999Z**, and its original job timestamps remained unchanged through the widget edits. This demonstrates preparation and reuse, not a claim of zero cold-start latency.
- ✅ Order invalidation/recompute — `test_approval_edit_and_widget_flow_use_committed_quantities` runs approval → ready → committed edit → new ready, including **3 → 4 → 3 → 4** and retry of a discarded key. `test_current_hash_never_serves_old_ready_result` and `test_queued_key_coalesces_and_stale_worker_is_discarded` also pass. Full backend command `.venv/Scripts/python.exe -m pytest backend/tests -q --basetemp=../scoop-runtime/pytest-n1-all-final` → **234 passed in 83.61 s**, saved in `reports/n1-backend-tests.txt`. Browser edit **112** changed the hash, reset later steps to Orders, showed its notice and scheduled a **running** job; Undo restored exact prior quantities. Widget cleanup also restored exact prior IDs/order.
- ✅ Removed page — `rg -n "Purchases|No purchases due|Orders due|export function Execution|function Purchase\(" frontend/src --glob "*.tsx"` → **no matches, exit 1**. Output in `reports/n1-static-checks.txt`. `git diff --check` passed; final `pnpm --dir frontend build` passed (53 modules).

Implementation contract: retain the internal draft/review/approved order status, use a separate persisted five-step view state, precompute after committed approval, and key persisted raw per-product replay series by effective order inputs. Widget changes and read-only requests must never schedule simulation work.


### N1 implementation and review

A persisted `SimulationRun` stores both policies' full per-product demand, arrivals, shipped, lost and closing-stock series, keyed by plan and effective order inputs. Approval schedules work after commit; widget layout, discussion and report content are excluded from the key. A single local worker coalesces repeated keys, rejects obsolete results, and retries a discarded key when the planner returns to those quantities. Read-only status and flow requests do not schedule work. Play runs at fixed 2×, waits at its final frame, and opens Results only on the explicit action.

Central review corrected three normal-flow issues: revisiting approved Orders still provides its primary action; Report context remains editable when revisited; draft context/Undo remains on Report without a misleading replay notice. A cancelled-key regression exercises quantities 3 → 4 → 3 → 4 through committed API edits. The final browser test also edits an order after Results, checks the later steps are invalidated, and restores the exact prior quantities and widget layout.

The first measured cold preparation took **37.203 seconds**, from 17:23:03.910 to 17:23:41.193 Asia/Shanghai. Subsequent identical approvals reuse the persisted result; the browser record explicitly distinguishes that reuse. This is not a claim that every cold run is instant: an early entry can show Preparing. A read-only profile identified forecast/rescoring work and repeated pandas metadata copies. Play now discards unused fitted-tree metadata before reading automatic order quantities; this changes neither predictions nor policy rules, and the 15 focused replay/job tests passed after that change.

Screens reviewed at 1440 × 1000: `n1-01-report.png` has a legible five-step bar and a distinct Review orders action; `n1-02-orders.png` puts Export and Approve in the order view with the sticky capacity bar; `n1-03-watch.png` shows widget editing and Next: Play without sub-tabs; `n1-04-play.png` separates the clock/widgets from the event feed; `n1-05-results.png` separates the outcome numbers and final widgets from playback. Early captures of loading/refresh and animation frames were rejected and retaken after settling. Existing cohort naming, tick rounding, subtitles and the richer Results reveal are the explicit N3 work below.

No live Gemini call was made in N1. Existing stored Gemini report content was displayed, and source data was not regenerated. The pre-scenario outcome remains **11,528 units short under this plan versus 10,191 under the rule**, with 36.6402 versus 44.6169 average pallets; N1 makes no performance-superiority claim.

## N2 — Hours and minutes

- ✅ Test — `test_hourly_reconciles_every_day_sku_and_policy` checks both policies, each day/product, all four hourly flows, every inventory balance and the closing endpoint. Full backend command `.venv/Scripts/python.exe -m pytest backend/tests -q --basetemp=../scoop-runtime/pytest-n2-all` → **238 passed in 83.98 s**, saved in `reports/n2-backend-tests.txt`.
- ✅ Test — `test_stockout_events_use_first_strict_exceedance` checks the first ten-minute point where requests exceed available stock. `test_profile_arrivals_and_events_are_timed_and_stable` checks morning supplier windows, monotone bounded profiles, timestamps, deterministic event IDs/order and unchanged daily simulation rows.
- ✅ Browser — `pnpm --dir frontend exec playwright test n2-clock.spec.ts --reporter=line` → **1 passed (49.6 s)**, real API and persisted simulation. `docs/screenshots/n2-01-midday.png` shows **20 Jul 12:40**, timed shortage events and **38.2 / 71.0 pallets**. `n2-02-final-frame.png` shows **4 Aug 23:50**, Replay and See results; `n2-03-results.png` shows completed final widgets. Pause preserves the exact minute; Resume advances; the final frame unlocks Results without jumping. Remaining replay took **31.212 s**, versus **30.931 s** expected. No page errors; quantities unchanged. Evidence: `reports/n2-clock.json` and `reports/n2-browser-tests.txt`.

The fixed profile puts receipts in supplier-specific morning windows, requests between 10:00 and 22:00 with an afternoon peak, supplier orders at the 14:00 cut-off, and dispatch between 18:00 and 22:00. Daily simulation remains the physical model. Hourly demand, dispatch, shortage and receipt **flows** sum to daily totals; inventory is a **level**, so its hourly changes and closing endpoint reconcile instead. Play advances ten minutes per tick at about two seconds per day, updates widget numbers and the cold-store gauge, redraws charts hourly, and reveals events at their timestamps. Results retain final daily values.

Central review removed superseded daily aggregate events, stopped early weather events from exposing full-day request totals, used actual receipt units in arrival text, and restored automatic playback when returning to an unfinished Play view. Finite-precision CDF accumulation is clamped to prevent negative tail flows. An initial browser run exposed cumulative timer drift; the clock now derives ten-minute positions from elapsed time, with the event feed reused between arrivals. A repeat pass also caught stale completion state when approving the same orders again; approval now resets playback while preserving the ready simulation.

The production payload reconciles **2 policies × 75 products × 16 days**, with **129,600** flow/level comparisons and maximum absolute error **9.095 × 10⁻¹³**. All **31** emitted shortage/comparison events use the first strict exceedance. Daily rows and per-product daily quantities are byte-equivalent under a canonical JSON fingerprint to the N1 result: `869c95766e04ff4cf66904084ec61cc6ce88fa66797b92412da976ce6dad40a4`; evidence in `reports/n2-daily-conservation.json`. The first timed result took **38.5 s** to precompute, then repeated approvals reused it. Frontend build passed (54 modules); `git diff --check` passed.

Visual review: the mid-day clock and cold-store gauge are readable in a single top row, timed events align in the right feed, and final Play keeps a clear See results action. The first Results capture showed a loading state and was rejected; the retained capture waits for all five final widgets. The pre-existing long negative cohort title and unrounded chart ticks are explicitly N3 work. Simplifications now state the fixed timing assumption. No live Gemini calls or world regeneration were used.

## N3 — UI polish

- ❌ Pending — Screenshots: native adjustment cards; evidence URL/modal with search, sorting and 25-row pagination; both All observations checkbox states; a positive cohort name; round axis ticks; Results reveal.
- ❌ Pending — Test: validator rejects an AI table that repeats card case/pallet numbers.
- ❌ Pending — Grep/API: no Early warnings UI string and no negative-only seed 93 cohort card name.

## N4 — Product illustrations

- ❌ Pending — Contact sheet of all 75 individually generated illustrations; inspect consistent style and regenerate exceptions.
- ❌ Pending — Screenshots: illustrations in Orders, a cohort card, a Play widget and an event.
- ❌ Pending — Test: every product renders an image or composed SVG fallback.

## N5 — Illustrative compound-trend scenario

- ❌ Pending — Report all scenario parameters, authorized algorithm fixes, and before/after numbers.
- ❌ Pending — Default week: strawberry × water-based × value-price cohort first, new that week; quiet week has no cards.
- ❌ Pending — Mango × Kowloon is a separate card, or record the actual reason it is absent.
- ❌ Pending — Screenshot: compound-cohort tree drill-down and change-versus-rest bars.
- ❌ Pending — Matched average pallets within 2%, at most six plan simulations; plan beats the rule on units short avoided, stockout product-days avoided, and lost margin avoided; screenshot.
- ❌ Pending — Illustrative label and Simplifications cover the scenario, intraday timing and matched-space comparison.

## N6 — Walkthrough and documentation

- ❌ Pending — Updated `frontend/e2e/walkthrough.spec.ts` passes the five-step flow; screenshots of each step, a mid-Play timed event and Results saved as `docs/screenshots/n6-*.png`.
- ❌ Pending — README, DEMO and TECHNICAL_DESIGN describe the delivered behavior; the summary above lists every phase with status and commit.

## Visual review record

For every changed screen, inspect the saved screenshot for hierarchy, legibility, alignment, whitespace and unnecessary repetition. Record the screenshot and concrete findings with the corresponding phase before accepting it.
