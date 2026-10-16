# Scoop: night handoff: Results wording + Guided tour

Same rules as before: branch `claude/scoop-prototype`; phases in order; every acceptance check ✅/❌ with evidence; push after each accepted phase; one-page summary at the top of `docs/overnight-report.md` (archive the previous report under `docs/reports/`).
**Copy rule:** every user-visible string below is final copy. Use it **verbatim**. Replace `{placeholders}` with the real values from the data, formatted as shown; do not reword anything else and do not add text. If a sentence cannot be true for the data, stop and report it; do not improvise new wording.
**Layout rule (still applies):** nothing stretches the page; panels scroll inside themselves; Play/Watch have no page scroll.
**Gemini:** stay within the remaining night-3 allowance; use it only to record the tour answers (T4).

---

## R0. Results: show both numbers and the lead

Replace the "… avoided" key numbers. Each of the three metrics becomes one card:

```
Units short
Simple rule   6,063          ← small, muted, with an orange dot
Scoop         4,297          ← key number, green
29% fewer                    ← small badge
```

| Card title | Rows | Badge |
|---|---|---|
| Units short | Simple rule {rule_units} · Scoop {scoop_units} | {pct}% fewer |
| Stockout product-days | Simple rule {rule_days} · Scoop {scoop_days} | {pct}% fewer |
| Lost margin | Simple rule HK${rule_margin} · Scoop HK${scoop_margin} | {pct}% less |

- Percent = (rule − scoop) / rule, rounded to a whole percent. If Scoop is not lower, the badge reads "{pct}% more" in coral (keep the code path honest).
- One muted line under the three cards: `Same cold store ({capacity} pallets) · same store demand · Simple rule = 28-day average + 25%`
- Remove every "avoided" key-number label and the "Illustrative scenario" line from Results.

**Acceptance**
- [ ] Results screenshot at 1440×900; numbers match the stored replay; grep shows no "avoided" on Results.

---

## T1. What the tour is

A **game-style tutorial on the real app**. Same screens, same components, same five steps.
- A large **coach card** says what to do now; everything except the current target is dimmed and not clickable.
- Every free-form or fine-tuning control is replaced by **choice cards**:
  - chat input → suggested questions;
  - Add context → three options;
  - the in-stock slider → fixed at auto, not interactive;
  - inline case edits → not available;
  - "+ Add widget" → three options.
- Real buttons stay real and are clicked by the user: Review orders, Approve orders, Next: Play, See results.

**Entry.** On first visit, the landing modal (copy in T5, "Welcome") offers the tour or Explore. A "Take the tour" link also sits in the top bar at all times.

**Exit.** "Skip tour" on every coach card and the Esc key end the tour and open Explore at the default week, in a clean state.

## T2. How it runs (no shared state, no live AI)

- **Tour bundle.** A build script produces `tour-bundle.json` by calling the **real API** on a clean copy of the default week and recording the exact responses each tour screen needs: report, cards, drill-down, orders, widgets, replay, results, chat answers. The bundle includes every branch (T3).
- **Fixture mode.** In the tour, the frontend renders the real components from the bundle. It sends **no writes** and **no provider calls**. Many people can take the tour at once; Explore and the database are untouched.
- The bundle is versioned with the default-week order hash. Rebuild it whenever the default week changes; a test fails if the hash is stale.

**Acceptance**
- [ ] Test: a full tour, including every branch, sends zero non-GET requests and zero provider calls; the database hash is identical before and after.
- [ ] Test: the stale-bundle check fails when the default-week hash changes.

## T3. Branches

- **Step 4 (Add context)** changes the orders. There are three options, so precompute **three** complete branches: orders, replay and results.
- **Steps 3 and 7** change only what is shown: the chat answer and the added widget.
- Later steps show the numbers of the chosen step-4 branch.

**Acceptance**
- [ ] The three step-4 branches have distinct stored orders/replay/results; the coach-card numbers and Results match the chosen branch.

## T4. Recorded AI answers

- For each suggested question (step 3) and each context option (step 4), record one real Gemini answer on the same snapshot, through the normal assistant path.
- Each answer must pass the existing numeric grounding check against the snapshot. Keep each answer to at most 3 short sentences; if one is longer, regenerate it once with that instruction.
- Store each answer with its provider metadata in the bundle. In the chat panel, the answer types out quickly (about 40 characters per frame) with a muted label "Recorded example".
- Step 4's answer is followed by the real context result: the card's before/after chip and its updated cases.

**Acceptance**
- [ ] All recorded answers pass grounding; their texts are listed in the report.

## T5. Steps and copy (verbatim)

The coach card has a step counter, a large instruction line (20/600), one small context line (15/400, muted), optional choice cards, and "Skip tour" on the right. It sits next to its target, never covering it, and points at it with a small arrow. The spotlight is a soft cutout around the target; the rest of the screen is dimmed at about 55%.

**Welcome (modal)**
- Title: `Plan a week of ice cream`
- Body: `It's Monday 27 July at the Tsing Yi cold store: 75 products, {capacity} pallets of space, and hot days ahead.`
- Buttons: `Start the tour` (primary) · `Explore on my own`

**Step 1 of 10 · Report**: target: "How we found it" on the strawberry card
- Big: `Open "How we found it"`
- Small: `Scoop flagged value strawberry water ices: {effect}% above forecast.`
- Advances when the user opens it.

**Step 2 of 10 · Report**: target: the drill-down rows
- Big: `See where the trend lives`
- Small: `Strawberry alone: +{l1}%. Add value price: +{l2}%. Add water-based: +{l3}%. The rest barely moved.`
- Button: `Next`

**Step 3 of 10 · Report**: target: the chat panel
- Big: `Ask Scoop about it`
- Small: `Pick a question.`
- Choice cards: `Why strawberry, and why now?` · `Could this just be the heat?`
- After the answer finishes, button: `Next`

**Step 4 of 10 · Report**: target: the strawberry card's context area
- Big: `Tell Scoop what you know`
- Small: `Your context is added to the evidence and the order is recalculated.`
- Choice cards: `A summer one-off, ending 10 Aug` · `I expect it to keep growing` · `Nothing to add`
- After the result shows, the small line changes to: `Strawberry order: {before} → {after} cases.` For "Nothing to add": `Strawberry order stays at {before} cases.`
- Button: `Next`

**Step 5 of 10 · Report**: target: "Review orders"
- Big: `Review the orders`
- Small: `Scoop has drafted this week's orders for all 75 products.`
- Advances when the user clicks Review orders.

**Step 6 of 10 · Orders**: target: the capacity bar, then "Approve orders"
- Big: `Check the cold store, then approve`
- Small: `{cases} cases this week · peak {peak} of {capacity} pallets.`
- Advances when the user clicks Approve orders.

**Step 7 of 10 · Watch**: target: the widget area
- Big: `Pick one more thing to watch`
- Small: `The four tiles at the top are always on.`
- Choice cards: `Strawberry stock` · `Cold-store space` · `Products closest to running out`
- After the widget appears, the big line changes to `Start the week` and the target moves to "Next: Play".

**Step 8 of 10 · Play**: target: the whole dashboard (no click needed; Play starts by itself)
- Big: `Watch the week happen`
- Small line changes with time (show each at its moment; values from the replay):
  - start: `Monday. This week's orders go out at 14:00.`
  - first heat day: `{date}: the heat arrives. Keep an eye on strawberry stock.`
  - first strawberry arrival: `{time} {date}: {units} strawberry ices arrive.`
  - first stockout, if any: `{time} {date}: {product} runs out.`
  - last frame: `{end_date}. The order has played out.`
- At the last frame the big line changes to `See the results` and the target moves to "See results".

**Step 9 of 10 · Results**: target: the three cards
- Big: `Here's how the week went`
- Small: `Same cold store, same demand: Scoop against a simple 28-day-average rule.`
- Button: `Next`

**Step 10 of 10 · End (modal)**
- Title: `That's Scoop`
- Body: `Now try it with your own choices.`
- Buttons: `Explore on my own` (primary) · `Replay the tour`

## T6. Behaviour details

- Enter or Space = the coach card's main action when it is a button; ← goes back one step where it makes sense (steps 2–4, 9).
- Coach card motion: it fades and slides (about 200 ms) to its next position; the spotlight moves with it. No other animation.
- Play in the tour runs at the normal fixed speed. The user cannot pause it, but "Skip tour" still works.
- Desktop only (1280 px and wider). Below that, the welcome modal offers Explore only.
- Each choice-card set has the same height and width; no card text wraps to more than two lines.

## T7. Tests, screenshots, docs

- `frontend/e2e/tour.spec.ts`: run the tour three times, once per step-4 branch, varying the step-3 and step-7 choices. Take a screenshot at every step into `docs/screenshots/tour-*.png` (1440×900).
- Check the coach card never overlaps its target, and the page never scrolls at the document level during Play.
- Update README / DEMO / TECHNICAL_DESIGN: the tour, fixture mode, recorded answers and the bundle rebuild command.

**Acceptance**
- [ ] All three runs pass; screenshots reviewed; copy matches this file exactly (a test compares the rendered strings with a copy table, after placeholders are filled).