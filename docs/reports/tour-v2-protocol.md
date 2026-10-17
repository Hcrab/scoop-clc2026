# Scoop: tour v2: new flow and copy, recalculation beats, Play speeds

Builds on the tour you already shipped (bundle, fixture mode, coach card, branches). Same rules: every acceptance check ✅/❌ with evidence; push when accepted; one-page summary at the top of the report.
**Copy rule:** all copy below is final. Use it **verbatim**, keep the **bold**, and replace `{placeholders}` with real values from the bundle. If a sentence cannot be true for the data, stop and report it; do not improvise wording.

## V1. Coach card

- **Title:** one line, 20/600.
- **Body:** up to three sentences, 15/400, with inline **bold** support. Render bold from `**…**` in the copy table.
- **Below the body:** optional choice cards or one button.
- **Skip tour** stays top-right.
- About 420 px wide; placed beside its target, never covering it.
- Steps are numbered "Step N of 14" (the welcome and end modals are not counted).

## V2. Recalculation beats (step 7)

Step 7 shows the recalculation as **four beats**. The spotlight moves to each target in turn; each beat holds for about 1.5 s, then a **Next** button appears.
1. The new context label on the strawberry card.
2. The expected-lift figure (bar or number) animating **{f_before}× → {f_after}×**.
3. The card's case count counting **{before} → {after}**.
4. The cold-store peak on the right column counting **{p_before} → {p_after}**.

For each step-4 branch, the bundle must store: `f_before`, `f_after` (cohort factor), `before`, `after` (cohort cases), `p_before`, `p_after` (projected peak), and, if a capacity cut happened, `n` (cases trimmed) with the trimmed products listed. For "Nothing to add", only beat 1 (no label) and the body text appear.

## V3. Play speed

Everywhere Play runs (Explore and tour): the default is **2×**, with a small segmented control **2× · 4× · 8×**. Playback reads the precomputed replay, so a speed change only changes the clock rate; events, numbers and captions stay in sync at every speed.

## V4. Flow and copy (verbatim)

**Welcome (modal)**
- Title: `Monday, 27 July`
- Body: `You plan stock for the **Tsing Yi cold store**: 75 products, **{capacity} pallets** of space, and this week's orders are due by 2 pm. This tour walks you through **one weekly cycle** in Scoop.`
- Buttons: `Start the tour` (primary) · `Explore on my own`

**Step 1 of 14 · target: the left report column**
- Title: `Read the weekly report`
- Body: `The left side is the **weekly report**. Every Monday, Scoop's AI writes it from recent store orders: **what changed**, and the evidence behind it. You can open any chart or source to check the numbers.`
- Button: `Next`

**Step 2 of 14 · target: the strawberry finding in the report**
- Title: `Look at the first finding`
- Body: `The first finding: value strawberry water ices are selling **{effect}% above forecast**.`
- Button: `Next`

**Step 3 of 14 · target: "How we found it" on the strawberry card** (advances when the user opens it, then shows `Next`)
- Title: `See where the trend comes from`
- Body: `This view shows how the trend was found by **combining several separate tags**. **Weather effects are removed before we measure trends**: a **LightGBM demand forecast** accounts for the weather, and **hierarchical Bayesian trend detection** looks at what is left. So this is a **change in taste**, not the heat, and you can see it more clearly than in a spreadsheet.`

**Step 4 of 14 · target: the right column**
- Title: `Check the suggested actions`
- Body: `The right side lists **suggested actions**. Each card shows what to order more or less of, **how many cases**, and the effect on the cold store. The **in-stock target** at the top sets how much safety stock all orders carry; Scoop sets it automatically from margin and storage cost.`
- Button: `Next`

**Step 5 of 14 · target: the chat panel**
- Title: `Ask the assistant (optional)`
- Body: `If something is unclear, you can **ask the assistant**. It answers from the **same data** as the report.`
- Choice cards: `Why strawberry, and why now?` · `Could this just be the heat?` · `Skip`
- After a recorded answer finishes (or after Skip): `Next`

**Step 6 of 14 · target: the strawberry card's context area**
- Title: `Add what you know`
- Body: `The data may miss things you know, such as a promotion ending or a one-off event. **Add it here** and Scoop **recalculates the order**.`
- Choice cards: `It's a summer one-off, ending 10 Aug` · `I expect it to keep growing` · `Nothing to add`

**Step 7 of 14 · recalculation beats (V2)**
- Title: `See how the order changes`
- Body, one-off branch: `With the trend ending on **10 Aug**, Scoop only adds stock for the days before it. Expected lift: **{f_before}× → {f_after}×** · Order: **{before} → {after} cases** · Cold-store peak: **{p_before} → {p_after} pallets**`
- Body, keep-growing branch: `With the trend expected to grow, Scoop raises its estimate. To stay within the cold store, it trims **{n} cases** from lower-value lines. Expected lift: **{f_before}× → {f_after}×** · Order: **{before} → {after} cases** · Cold-store peak: **{p_before} → {p_after} pallets**`
  - If no cut happened, drop the sentence "To stay within the cold store, it trims **{n} cases** from lower-value lines."
- Body, nothing-to-add branch: `No context added, so Scoop keeps the estimate based on the data: **{before} cases**.`
- Button: `Next`

**Step 8 of 14 · target: "Review orders"** (advances on click)
- Title: `Review the orders`
- Body: `Click **Review orders** to see this week's full order.`

**Step 9 of 14 · target: the order list** (the strawberry line's order evidence is open)
- Title: `Check the order lines`
- Body: `This page lists **every order line** for this week. Open a line to see how its quantity was calculated: the **forecast**, stock **on hand and on the way**, and any **adjustment**. The bar at the top shows the cold store's **projected peak**.`
- Button: `Next`

**Step 10 of 14 · target: "Approve orders"** (advances on click)
- Title: `Approve the orders`
- Body: `When the order looks right, click **Approve orders**.`

**Step 11 of 14 · target: the Watch dashboard**
- Title: `Choose what to follow`
- Body: `This page is where you **follow stock after the order is placed**. The tiles at the top track the **overall health** of the warehouse; the cards below follow **specific products**. Add one more card to follow.`
- Choice cards: `Strawberry stock` · `Cold-store space` · `Products closest to running out`
- After the card appears, the step advances automatically.

**Step 12 of 14 · target: "Next: Play"** (advances on click)
- Title: `Start the next two weeks`
- Body: `Click **Next: Play** to see how the next two weeks unfold.`

**Step 13 of 14 · target: the whole Play view**
- Title: `Follow the two weeks`
- Body: `This view plays the next two weeks **hour by hour**. The cards update as stock **arrives and sells**; the list on the right records **each event**. You can speed it up with **4×** or **8×**.`
- Event line under the body (shown at its moment, plain statements):
  - `{date}: heat begins ({temp}°C).`
  - `{time} {date}: {units} strawberry ices arrive.`
  - `{time} {date}: {product} runs out.`
- At the last frame the body becomes: `The two weeks are over. Click **See results**.` The target moves to "See results"; the step advances on click.

**Step 14 of 14 · target: the three Results cards**
- Title: `Compare the results`
- Body: `This page compares your plan with a **common rule**: order the **28-day average plus 25%**. Both use the **same cold store** and the **same store demand**. Each card shows the rule's result, Scoop's result and the difference.`
- Button: `Next`

**End (modal)**
- Title: `End of the tour`
- Body: `That's one weekly cycle: **read the report**, **add what you know**, **approve the orders** and **follow the results**. You can now explore on your own.`
- Buttons: `Explore on my own` (primary) · `Replay the tour`

## V5. Results (if not already done)

Each metric card shows `Simple rule {x}` (small, orange dot) · `Scoop {y}` (key number, green) · a badge `{pct}% fewer` / `{pct}% less`; one muted line below: `Same cold store ({capacity} pallets) · same store demand · Simple rule = 28-day average + 25%`. No "avoided" labels.

## Acceptance

- [ ] The tour runs three times (one per step-6 branch), with screenshots of every step and of each of the four step-7 beats, in `docs/screenshots/tour2-*.png` at 1440×900.
- [ ] A test compares every rendered tour string with this copy table after placeholders are filled; bold renders as bold.
- [ ] Step-7 numbers match the bundle and the following Orders / Results screens for that branch.
- [ ] Play speed: switching 2×/4×/8× mid-play keeps events and numbers in sync (test); default is 2×.
- [ ] No page-level scroll on Play and Watch; the coach card never covers its target.