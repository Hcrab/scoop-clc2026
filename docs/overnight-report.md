# Scoop: Results and guided tour — 17 October 2026

## One-page summary

**R0 and the guided-tour phase are accepted.** R0 was pushed as `b6505cf`; the accepted tour is ready for its phase commit/push on `claude/scoop-prototype`. The previous report is archived at [pre-tour-20261016.md](reports/pre-tour-20261016.md). Final copy and requirements: [night4-protocol.md](reports/night4-protocol.md).

| Check | Status | Evidence |
|---|---|---|
| R0 Results | ✅ | Real 1440×900 screenshot, replay values and no rendered “avoided” |
| T1 Real app tutorial | ✅ | Ten native-component steps, welcome/top-bar entry, Skip/Esc and replay |
| T2 No shared state or live AI | ✅ | All three full tours: zero HTTP non-GET requests; every public-table hash and provider usage unchanged; stale source rejected |
| T3 Context branches | ✅ | Distinct actual orders, product replays and Results in all three branches |
| T4 Recorded Gemini | ✅ | Five real grounded answers; metadata, evidence and snapshot hashes saved |
| T5 Copy/layout | ✅ | Rendered copy-table comparison; 55 reviewed 1440×900 screenshots; zero target overlap |
| T6 Behavior | ✅ | Keyboard/back/exit/replay checks, fixed-speed Play, internal scrolling, narrow Explore-only welcome |
| T7 Tests/docs | ✅ | 23 frontend checks, 6 backend checks, 6 browser checks plus 3 focused Explore checks; build passed; README/DEMO/design updated |

| Context | Strawberry cases | Total initial cases | Units short | Stockout product-days | Lost margin |
|---|---:|---:|---:|---:|---:|
| unchanged | 241 | 2,413 | 4,297 | 36 | HK$24,271.33 |
| summer | 209 | 2,381 | 5,012 | 40 | HK$27,444.98 |
| growing | 246 | 2,418 | 4,219 | 34 | HK$23,909.21 |

The unchanged rule is 6,063 short units / 39 product-days / HK$30,849.11. The summer choice genuinely worsens product-days against it: the badge shows **3% more** in coral. No thresholds, priors, buffers, costs, source data or results were tuned in this handoff. The growing choice is a fixed optimistic user-context preset from the existing interval, not a search for better Results.

Gemini was used only for T4: **11 provider calls / $0.322931** for initial recordings, numeric-evidence corrections and context confirmations. Cumulative **$18.649068 / $26.897085**, leaving **$8.248017**. Tour playback spends zero. The local LOGFLOWS PDF and its builder/assets remain excluded from published history. [UI copy CSV](ui-copy.csv) refreshed to **4,478 rows**, including tour copy and the five recorded replies; no pending user copy revisions were invented.

## R0 — accepted

- ✅ Three real comparison cards: Units short **Simple rule 6,063 / Scoop 4,297 / 29% fewer**; Stockout product-days **39 / 36 / 8% fewer**; Lost margin **HK$30,849 / HK$24,271 / 21% less**. Evidence: [stored replay and rendered values](../reports/night4/r0-results.json), [1440×900 screenshot](screenshots/r0-results.png), personally reviewed.
- ✅ The muted footer matches the handoff verbatim. `rg -n -i avoided reports/night4/r0-results-ui.txt` → exit **1**, no matches. Removed the Results Illustrative scenario line and old duplicate footer paragraphs.
- ✅ `node --test frontend/tests/results-metrics.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/report-product-icons.test.cjs` → **18 passed**; `pnpm --dir frontend build` passed. Equal and worse badges use coral `more`; a positive Scoop loss against a zero rule has no fabricated finite percentage. The default replay has no zero denominator.
- ✅ No algorithms, thresholds, costs, buffers, stored orders or replay values changed. Local PDF and its rebuild assets remain excluded from published history; the original local commit is retained on `local/logflows-overview-20261016`. Gemini before recording: **177 calls / $18.326137** against the night-3 cumulative cap **$26.897085** (remaining **$8.570948**).



## T1–T3 — real components, isolated data, three branches

- ✅ First visit offers the exact welcome; Take the tour is in the top bar. The same App, cohort drilldown, ActionList, Dashboard, Play and Results render underneath the coach. Review orders, Approve orders, Next: Play and See results retain their native handlers. Choice cards replace free chat/context/widget editing; the service slider is fixed at auto and inline edits are disabled.
- ✅ Skip and Esc discard only browser-local tour state and remount Explore at the default Report. Existing Explore evidence deep links are preserved. End replay starts a fresh local tour. Evidence: `frontend/e2e/tour.spec.ts` and [focused exit/link checks](../reports/night4/tour-explore-tests.txt).
- ✅ The builder calls the real API on a clean private clone, with independent sequences and no ground-truth table. All public-table fingerprints remain unchanged. Two independent clean builds gave identical physical branch signatures. Evidence: [build report](../reports/night4/bundle-build.json), `test_recording_schema_is_independent`.
- ✅ Full tours, including context, question and widget choices, issue **zero HTTP non-GET requests**, make zero provider calls and leave **every public-table hash identical**. Evidence: [summer](../reports/night4/tour-summer.json), [growing](../reports/night4/tour-growing.json), [unchanged](../reports/night4/tour-unchanged.json). The runtime's nine context/widget combinations also pass; unsupported routes never fall through to live HTTP.
- ✅ The source endpoint runs a READ ONLY transaction, using saved plan/orders/context in memory and current physical SELECTs. `test_source_endpoint_is_read_only` captures **zero SQL INSERT/UPDATE/DELETE/DDL**. Stale default hash fails `test_stale_hash_rejected`, the runtime loader check and the browser entry check.
- ✅ Each step-4 branch has distinct stored orders, per-product replay and aggregate Results. Coach order totals/peak and all three Results cards match the chosen branch in each full browser run. Question/widget choices only change display. Evidence: `test_each_physical_component_must_differ`, `test_generated_real_bundle`, three run JSONs and screenshots.

## T4 — recorded answers

- ✅ All five are genuine **gemini-3.8-flash** answers through the normal `/chat` path on the corresponding isolated snapshot; numeric grounding passes against saved report/context/tool evidence. Stored provider/model, usage, trace, claims/evidence, snapshot hash and physical order hash are checked again by `test_recorded_answers_are_genuine_grounded_and_on_their_branch`.
- ✅ Each accepted answer has at most three sentences. One initial question-recording attempt was rejected because its evidence collection omitted numeric query results already in the saved report. The evidence collection was corrected; the checker was not relaxed. Context confirmations were re-recorded to use the actual context before/after totals rather than the original report's +134-case uplift. Rejected/earlier attempts remain in the [recording audit](../reports/night4/recorded-answers.json).
- ✅ The real chat panel labels answers **Recorded example**, types at about 40 characters per frame and then enables Next. Applied context shows the native real EditReceipt; unchanged has no fabricated edit. Evidence: `tour-*-03-answer.png`, `tour-*-04-result.png` and browser text assertions.

### why

> Over the last 14 days, store replenishment requests for value water-based strawberry ice bars surged to 15,785 units—running 44.6% above model expectations—whereas creamy strawberry lines remained flat (-0.6%).
>
> While typical summer weather explains baseline seasonal volume, it does not account for this sharp, format-specific spike or the resulting 88.2% warehouse fill rate caused by recent supplier delivery delays.
>
> No recorded promotions or localized campaigns explain the surge, making sustained demand for light, thirst-quenching fruit bars our working interpretation.

### heat

> While summer warmth does lift category baseline demand, the +44.6% surge in store replenishment requests for value water-based strawberry bars is measured against expectations that already factor in historical weather and seasonal patterns.
>
> Furthermore, comparable value creamy strawberry bars tracked their weather-adjusted expectation almost flatly (-0.6% deviation), showing the lift is concentrated specifically in the water-ice format.
>
> Unusual heat alone cannot account for this relative disparity, making format-specific store demand shifts or unrecorded promotional activity worth keeping under review.

### summer

> Setting this surge as a summer one-off ending 10 August adjusts the value-price strawberry water-ice purchase down from 241 to 209 cases, rather than treating the elevated replenishment as permanent. While weather-adjusted models account for general summer heat driving interest in light water-based treats, they do not explain why demand spiked exclusively for strawberry water bars (+44.6% deviation) while creamy strawberry bars stayed flat (-0.6%). Planning an early August taper captures the ongoing surge while curbing the risk of over-ordering once peak temperatures and seasonal demand subside.

### growing

> The optimistic context override applies the upper end of the estimated sustained demand effect (+41.3%) to value strawberry water-based bars across all four districts, raising the cohort's order from 241 to 246 cases.
>
> While sustained summer heat accounts for broad category volume, store replenishment requests outpaced baseline expectations by 44.6% over the last 14 days, pointing to format-specific demand beyond weather alone.
>
> Note that observed replenishment demand reflects store ordering rather than direct consumer checkout sales, and increasing order quantities cannot ensure future store fill rates without timely supplier deliveries.

### unchanged

> Store replenishment orders for value water-based strawberry ice bars reached 15,785 units against a weather-adjusted expectation of 10,913 units (+44.6%), showing demand running well above what model temperature sensitivity alone accounts for. Delivery delays on four supplier shipments caused warehouse fulfillment to drop to 88.2%, leaving 1,859 requested units unfulfilled. With no context changes added, the saved purchasing plan remains steady at 241 cases for this cohort.

## T5–T7 — copy, behavior, screenshots and docs

- ✅ Big/small copy, counters, choices, welcome/end text and actual placeholder values are compared to `frontend/src/tour/copy.ts`. Native app labels remain native; no slogans or extra coach explanations were added. The growing interval endpoint is an explicit selectable expectation, not a hidden model change.
- ✅ Coach uses 20/600 instruction and 15/400 muted context, an arrow and approximately 55% dimming. Each choice set has uniform width/height and one-line labels at 1440 px. All measured coach/target intersections are zero. Final screenshots reviewed across every step and every branch: [review manifest](../reports/night4/screenshot-review.json).
- ✅ Enter/Space advances the coach's main button; Left returns at the permitted steps, including completed Results → Play without restarting it. Esc/Skip exits, and the end Replay button resets the local tour. Narrow welcome only offers Explore. Fixed-speed Play retains the original 2,000 ms/day timer; Pause/Resume/Replay are hidden there. Its coach changes at the recorded receipt, heat, stockout and end moments; no dates/events were forced.
- ✅ Tour-only body containment removes the browser's extra document scroll range; Report panes, Watch dashboard, Play dashboard/feed and Results scroll internally. Play document height equals the viewport throughout all three runs. No general Explore layout/scroll refactor was applied. Existing evidence links have a focused browser regression check.
- ✅ `pnpm --dir frontend build` passed. `node --test frontend/tests/tour-runtime.test.cjs frontend/tests/results-metrics.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/report-product-icons.test.cjs` → **23 passed** ([output](../reports/night4/tour-unit-tests.txt)). `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_tour_bundle.py -q` → **6 passed** ([output](../reports/night4/tour-backend-tests.txt)).
- ✅ `SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour.spec.ts --reporter=line` → **6 passed**, including the three complete branch runs, stale/narrow entry, keyboard/exit/re-entry and ordinary Explore evidence links ([output](../reports/night4/tour-browser-tests.txt)). The focused `--grep 'stale source|Esc exits|Explore preserves'` run also → **3 passed** ([output](../reports/night4/tour-explore-tests.txt)). Final screenshots include the tour-only removal of a developer preset note; actual context data, receipt and order quantities are unchanged.
- ✅ README, DEMO and TECHNICAL_DESIGN describe entry, choices, fixture isolation, recordings, source fingerprint/staleness and rebuild commands. `scripts/build-tour-bundle.py` rebuilds real data; `scripts/record-tour-answers.py` records the five answers separately with configured credentials/allowance; then build the frontend. The checked-in completed bundle can be replayed without a live AI key.
