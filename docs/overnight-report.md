# Scoop: order ledgers, tour futures and walkthrough timing — 17 October 2026

## One-page summary

**The tour review phase is accepted.** All 75 order lines have an arithmetical ledger; the three tour context choices now have separate strawberry futures; Watch supports multi-selection. Three additional paced runs estimate the actual experience. Prior acceptance is archived in [tour v2](reports/tour-v2-20261017.md); requirements are in [the review protocol](reports/tour-review-protocol.md).

| Acceptance | Status | Evidence |
|---|---|---|
| Ledger on every line; all 75 reconcile | ✅ | `test_all_75_real_default_api_lines_and_export_are_read_only`; `test_generated_tour_ledgers_reconcile_all_75_lines_in_every_branch`; MOQ/cut/rounding/surplus/edit cases |
| Trend note only on matching presented cohort; plain UI labels | ✅ | 14 named-cohort notes / 61 without; with/without screenshots; exported UI-copy grep has zero banned matches |
| Identical history; distinct futures and actual policy replays | ✅ | Private SQL row proofs; original noise/weather/non-cohort hashes; context-free baseline controls; unchanged replay exactly reproduces original |
| Step-7 muted notice | ✅ | Exact rendered notice in all three full browser flows |
| Step-11 toggle, minimum one, Add selected, atomic add and reset | ✅ | Every nonempty subset in all branches; browser selects two, deselects to zero, adds both and verifies real cards |
| Screenshots: both ledger states, two selected, all three Results | ✅ | 80 reviewed 1440×900 screenshots; `reports/tour3/screenshot-review.json` |
| Three normal paced branch walkthroughs | ✅ | [Timing report](reports/tour-duration-20261017.md); per-step JSON; zero errors/HTTP writes |

**Validation:** 53 backend checks, 35 frontend checks, seven browser acceptance checks, three paced walkthroughs, production build and diff check pass. No new Gemini calls/spend. Public database and provider fingerprints match before/after. LOGFLOWS PDF and launcher changes remain local and excluded from this commit.

## Actual branch Results

| Branch | Policy | Units short | Stockout product-days | Lost margin |
|---|---|---|---|---|
| summer | Scoop | 4,868 | 40 | HK$26,802.02 |
| summer | Simple rule | 5,919 | 39 | HK$30,206.15 |
| growing | Scoop | 4,997 | 39 | HK$27,475.13 |
| growing | Simple rule | 7,311 | 42 | HK$36,394.79 |
| unchanged | Scoop | 4,297 | 36 | HK$24,271.33 |
| unchanged | Simple rule | 6,063 | 39 | HK$30,849.11 |

Compare policies **within** a branch: each receives identical store demand and the same cold-store capacity. The Simple rule is context-blind and unchanged; its rolling history naturally differs between futures. Summer has 40 versus 39 product-days and correctly displays **3% more** in coral. No outcome was forced or parameter tuned. Unchanged preserves the original 4,297 / 36 / HK$24,271.33 Scoop result and 6,063 / 39 / HK$30,849.11 rule result.

## Orders and context semantics

The median already includes the applied product factor. Safety is the real target minus that median; independently rounded display values use an explicit whole-unit residual rather than changing the buffer. Net demand, packing ceiling, actual supplier minimum, capacity cut and explicit final replacement quantities reconcile to the actual order. Ordinary lines show the final quantity once; adjusted lines separate the pre-adjustment case count from the final quantity. The ledger occupies the full row below each product so expanding it does not distort the table.

The forecast caption deliberately says **Expected sales over the next … days**: the production window extends through the next replenishment cycle, which is not necessarily the first inbound receipt. This corrects the supplied “until next delivery” wording without changing days or forecast. The trend note names only an actual matching presented cohort; small remainder-leaf factors remain in the forecast. Technical keys receive known display labels; free AI prose is not filtered. Grep evidence: `reports/tour3/copy-grep.json`, over all exported source/runtime copy.

## Future construction and provenance

`tour_worlds.py` changes only matched strawberry SKUs from 27 July in a private schema. It scales the same seed-93 store/SKU/day realization by desired planted multiplier / 1.5, rounding half up. Summer keeps 1.5 through 10 August then returns to 1.0; growing rises from 1.5 to 1.7 on 11 August; unchanged remains exact. History, other SKUs and weather match. Persisted and memory replay caches are cleared. Initial decisions see unchanged history and existing context overrides; later weekly fits use only elapsed branch history. Each branch's actual demand is identical in both policy outputs; independent context-free baseline controls agree.

The same saved `ends_on` and optimistic upper-interval `expect` presets remain: strawberry cases 209 / 246 / 241, full-plan cases 2,381 / 2,418 / 2,413. Case quantities and planning peaks match Step 7, Orders and Results. Planted demand multipliers are synthetic future definitions, distinct from the historically estimated 38% cohort lift. Full proofs and traces: `reports/night4/bundle-build.json` and `reports/tour3/data.json`.

The two genuine Gemini question replies preserve their original full `question_evidence` snapshot and hashes; historical report/findings are checked before reuse. Obsolete context answer recordings are removed. New ledger fields do not get falsely relabelled as the original grounded snapshot. Browser fixtures remain local and send zero non-GET HTTP requests. Public tables and provider usage are unchanged. The stale-source rejection, Escape/Skip, keyboard/back, replay and Explore evidence deep links pass.

## Browser review and duration

Three complete acceptance flows check every step, bold copy, recalculation beat, selected-widget merge, native 2×/4×/8× changes, event captions, branch figures and Results. There are 7,116 sampled animation frames with zero coach/target overlaps. Watch/Play retain internal panel scroll and 900px document height. Two actual integration issues were corrected: CSS checkmarks no longer alter button accessible names, and all selected cards are added before scrolling to the last added card.

The final ledger simplification was checked by component tests, a focused no-trend browser screenshot and the three paced native-component runs. All other acceptance screenshots retain the same geometry and data. [Screenshot review](../reports/tour3/screenshot-review.json). Paced results:

| Branch | Question | Added widgets | Playback speed | Whole experience | Actual replay |
|---|---|---|---|---|---|
| summer | why | stock + space | 2× | 5:21 | 32.0 s |
| growing | heat | space + cover | 4× | 5:03 | 16.2 s |
| unchanged | skip | stock | 8× | 4:29 | 8.2 s |

The pacing model is 200 English words/minute plus explicit inspection dwell; it is a reproducible experience estimate rather than human-subject evidence. The Play reading occurs during playback. Loading, welcome/end and actual clicks are included. Raw timestamps and word counts are saved per run.

## Reproduction and publication

```sh
python scripts/rebuild-tour-worlds.py
PYTHONPATH=backend python -m pytest backend/tests/test_order_ledger.py backend/tests/test_tour_worlds.py backend/tests/test_tour_bundle.py backend/tests/test_play.py -q
node --test frontend/tests/tour-copy.test.cjs frontend/tests/tour-runtime.test.cjs frontend/tests/order-ledger.test.cjs frontend/tests/data-labels.test.cjs frontend/tests/playback-clock.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/results-metrics.test.cjs
pnpm --dir frontend build
SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour.spec.ts
SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour-duration.spec.ts
node scripts/export-ui-copy.cjs --base-url http://127.0.0.1:8008
git diff --check
```

Logs are in `reports/tour3/`. The backend/API and source were reviewed centrally after all three bounded implementation owners completed. README, DEMO, TECHNICAL_DESIGN and UI copy inventory are updated. The previous launchers and local PDF are preserved outside the accepted changes. Publish only this phase on `claude/scoop-prototype` and verify remote HEAD.


## Watch widget reveal — follow-up

- ✅ Checking a Step-11 choice immediately previews its real native widget, scrolls the Watch panel to it in 280 ms and plays a 420 ms scale pop. Unticking removes the preview; Add selected confirms without duplicates and continues to Step 12.
- ✅ Rapid selections target the most recent choice; the coach remains visible and document scroll stays at zero. Reduced-motion preference uses immediate positioning without scale.
- ✅ 11 focused runtime checks and one native browser check pass. The browser covers individual choices, untick/recheck, rapid two-choice selection, confirmation and zero HTTP writes/errors. It captures 472 frames / 111 distinct scroll positions; both cards scale from about 0.965 to 1.024 before settling.
- ✅ Parent reviewed [the final Watch screenshot](screenshots/watch-widget-reveal.png); build and diff check pass. Evidence: `reports/widget-reveal/`, `frontend/e2e/widget-reveal.spec.ts`. Existing data, results and other screens are unchanged.
