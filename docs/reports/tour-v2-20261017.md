# Scoop: guided tour v2 — 17 October 2026

## One-page summary

**Tour v2 is accepted.** Fourteen numbered coach steps, unnumbered welcome/end, final verbatim copy with bold, four recalculation beats and native 2× / 4× / 8× playback are implemented. All five acceptance checks below pass. Prior report: [tour v1](reports/tour-v1-20261017.md). Requirements: [verbatim v2 handoff](reports/tour-v2-protocol.md).

| Acceptance | Status | Evidence |
|---|---|---|
| Three complete tours; every step/beat at 1440×900 | ✅ | Summer/why/stock, growing/heat/space, unchanged/Skip/cover; 76 reviewed screenshots including three Explore views |
| Rendered strings match final copy; bold renders bold | ✅ | Protocol-to-copy unit checks; every rendered title/body, placeholder and strong span checked in three browser runs |
| Step-7 values match bundle, Orders and Results | ✅ | Real recorded factors/cases/projected peaks; group quantities and all three Results metrics verified per branch |
| Speeds stay synchronized; default 2× | ✅ | Same day-5 frame at all speeds: identical 49 events, four tiles and widget numbers; 2→4→8 mid-play checks |
| No Watch/Play document scroll; no target overlap | ✅ | Tour and Explore height checks; 7,076 rendered-frame geometry samples with zero overlaps, plus stable-step checks |

| Branch | Cohort factor | Strawberry cases | Projected peak | Units short / product-days / lost margin |
|---|---|---|---|---|
| Summer | 1.38× → 1.30× | 241 → 209 | 61.3 → 61.4 pallets | 5,012 / 40 / HK$27,444.98 |
| Growing | 1.38× → 1.39× | 241 → 246 | 61.3 → 61.3 pallets | 4,219 / 34 / HK$23,909.21 |
| Unchanged | 1.38× → 1.38× | 241 → 241 | 61.3 → 61.3 pallets | 4,297 / 36 / HK$24,271.33 |

**Validation:** 24 frontend unit checks, 10 backend checks, 7 browser checks; production build and diff check pass. **Zero new Gemini calls or spend.** Every tour sends zero HTTP non-GET requests; all 29 public-table fingerprints and provider usage remain unchanged. Recorded snapshots and five grounded answers are preserved. No algorithms, thresholds, priors, buffers or world data were tuned. UI copy inventory refreshed. LOGFLOWS PDF stays local and excluded from publication.

## Acceptance evidence

- ✅ **Three full tours and screenshots.** [Browser output](../reports/tour2/browser-tests.txt); [summer](../reports/tour2/tour-summer.json), [growing](../reports/tour2/tour-growing.json), [unchanged](../reports/tour2/tour-unchanged.json). Every numbered step 1–14 is captured, plus welcome/end, expanded evidence, optional answers and replay events. Summer and growing include all four 1.5-second beats and final endpoints. Unchanged includes only beat 1, as explicitly specified. [Screenshot review manifest](../reports/tour2/screenshot-review.json) lists dimensions, hashes and review notes.
- ✅ **Exact rendered copy and bold.** `frontend/tests/tour-copy.test.cjs` compares the copy table with the supplied protocol. `frontend/e2e/tour.spec.ts` compares actual rendered title/body/counter/choices with filled copy and checks every bold segment is a `strong` element. All titles are single-line 20/600, bodies 15/400, coach width 420 px. Welcome, end, answers, event captions and optional Skip are exercised. [Unit output](../reports/tour2/unit-tests.txt).
- ✅ **Branch numbers.** [Read-only metadata report](../reports/tour2/data.json), `test_generated_real_bundle`, `test_factor_uses_actual_sku_factors_and_only_matched_expected_demand`, `test_only_new_capacity_cuts_are_counted` and three real-component browser flows. Step 7 shows and animates actual saved figures; Next is absent until the last beat completes. Following Orders confirms the cohort total and projected peak; Results confirms all three saved metrics. No branch adds capacity cuts: `n=0`, `trimmed_products=[]`; the growing sentence about trims is omitted under the authorized exception. [Backend output](../reports/tour2/backend-tests.txt).
- ✅ **Playback clock.** [Speed browser output/data](../reports/tour2/play-speed.json): day 5, 31 Jul 00:00, is identical at 2×, 4× and 8× (49 events; 100% fill, 0 stockouts, 4 low-cover products, 48.9/62 pallets). Mid-play switches retain the displayed tick: 29 Jul 00:00 at 2× → 2 Aug 00:00 at 4× → 10 Aug 00:00 at 8×, with 28/77/168 elapsed events. Actual UI tiles are checked against replay health at each cursor, and native event rows against the real event sequence. Unit tests also cover every ten-minute tick, midnight and completion. Default 2× and all segments are checked in Explore and tour.
- ✅ **Scrolling and geometry.** Three tours check stable targets and sample every rendered animation frame; zero overlap in 7,076 samples. Both Watch and Play have document height 900 and scrollY 0 at 1440×900; dashboard and feed scroll internally. Explore Watch/Play are tested separately. The report finding is targeted through its real opaque iframe with source/channel validation; sandbox remains `allow-scripts`. The coach relocates before paint, then fades/slides 7 px over about 200 ms in its adjacent gap, rather than crossing the target.

## Data definitions and retained behavior

The cohort factor is the expected-recent-demand-weighted arithmetic mean of actual per-SKU `f50` values for the four matched strawberry SKUs. Each SKU can retain a different calendar-sensitive factor. Cases sum effective orders. Peak is the **planning projection**, not the physical replay peak; one decimal is retained even when two endpoints round to the same value. New trims count only increases in per-SKU `capacity_cut_cases` over the clean base. [Exact full-precision inputs](../reports/tour2/data.json).

The bundle retains its original pristine order hash, all API responses, snapshots and five genuine grounded Gemini 3.8 Flash answers. V2 enrichment only adds recalculation annotations and actual 30 July `WeatherDaily.tmax` **33.6°C**, read-only. The first strawberry receipt is 08:10 on 27 July, 1,160 units from the existing pipeline; it is not attributed to the later 14:00 order. The synthetic world separately plants the strawberry combination and weather intervention; this explains the supplied tutorial narrative without introducing a new causal estimator.

R0 Results remains intact: Simple rule = 6,063 units short / 39 product-days / HK$30,849.11; unchanged Scoop = 4,297 / 36 / HK$24,271.33. Summer honestly displays **3% more** product-days in coral (40 vs 39). The local LOGFLOWS PDF, its builder and assets are not staged or pushed.

Tours send zero HTTP non-GETs and make no provider calls. The separate Explore speed test uses the native Watch/Play navigation and restores the original flow step; complete public-table and provider fingerprints match before/after. `test_stale_hash_rejected` and the browser stale-source test reject mismatched recordings. Narrow welcome, Skip/Esc, keyboard/back, replay and Explore evidence deep links pass.

## Commands and documentation

```sh
PYTHONPATH=backend python -m pytest backend/tests/test_tour_bundle.py -q
node --test frontend/tests/playback-clock.test.cjs frontend/tests/tour-copy.test.cjs frontend/tests/tour-runtime.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/results-metrics.test.cjs
pnpm --dir frontend build
SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour.spec.ts play-speed.spec.ts
node scripts/export-ui-copy.cjs --base-url http://127.0.0.1:8008
git diff --check
```

The executed Windows commands use the repository `.venv` and bundled Node/pnpm paths. [Build output](../reports/tour2/build.txt). README, DEMO and TECHNICAL_DESIGN describe the fourteen-step flow, version-2 bundle, read-only enrichment, real factor/peak definitions and shared playback speeds. [UI copy CSV](ui-copy.csv) retains columns `id, screen, component/file, current text`; no unrelated copy changes were applied.

No failed or blocked acceptance items remain. Source, data, screenshots, tests and this report accompany the accepted phase on `claude/scoop-prototype`; publication is verified against remote HEAD after push.
