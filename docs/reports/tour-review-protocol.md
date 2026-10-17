Three changes from the tour review.

1. Order evidence in plain words (Orders page, every line)
Replace the "protection period / p50 / service point / position" text with a small ledger that adds up:

  How we got {cases} cases
  Expected sales until the next delivery ({days} days)   {p50}      [muted: incl. +{pct}% {cohort} trend]
  Safety buffer for the {target}% in-stock target        +{buffer}
  Already in the cold store                              −{on_hand}
  Already on the way                                     −{on_order}
  Still needed                                           {need} units → {cases} cases ({units_per_case} per case)

- The muted trend note appears only when a cohort adjustment applies.
- If a capacity cut or MOQ changed the result, add one line before "Still needed":
  "Trimmed to fit the cold store  −{cut}" or "Rounded up to the supplier minimum  +{moq}".
- No "p50", "protection period", "service point" or "position" anywhere in the UI (grep).
- Test: every ledger adds up to its case count for all 75 lines.

2. Tour: each context choice is its own future ("parallel worlds")
- Before 27 Jul all three branches are identical (same report, same findings).
- From 27 Jul, store demand in each branch follows the chosen context:
  - "A summer one-off, ending 10 Aug": the strawberry cohort's uplift returns to its normal level after 10 Aug.
  - "I expect it to keep growing": the uplift keeps rising, reaching about +70% by 11 Aug.
  - "Nothing to add": the current scenario.
- In each branch, both policies face that branch's demand; the Simple rule is unchanged and ignores
  context. Recompute orders, replay and results per branch for the tour bundle.
- Tour only; Explore keeps the single default world.
- Step 7 gets one extra muted line: "In this tour, the next two weeks follow the context you chose."
- Report the three Results numbers per branch.

3. Tour step 11 "Choose what to follow": multi-select
- The three choice cards toggle on/off (at least one must be selected).
- A primary button "Add selected" adds all chosen cards at once, then the step advances.

Acceptance: screenshots of an order ledger (with and without a trend note), step 11 with two cards
selected, and Results for each of the three tour branches.


## Paced walkthrough follow-up

User: 按照提示正常跑几次，不同支线，看看大概体验时间。

Run all three choices through the real prompts with reading and inspection dwell, record wall time and playback time separately, and state the reading model explicitly.
