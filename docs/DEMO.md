# Demonstration guide

This walkthrough uses the designed synthetic seed-93 world: 75 products, 20 stores, one distribution centre, eight suppliers and a 60-pallet cold store. The public plan opens on **27 July 2026** (`P20260727`). First-plan preparation may take several minutes. The app does not place real supplier orders.

## 1. Report

Read the weekly report and open the first change card, **Strawberry → Value price → Water-based**. Its four products are IC006, IC061, IC062 and IC063. The estimated change is **+38.1552%**, with an 80% interval of **+35.1210% to +41.2575%**. Expand the card's right-side tree or its evidence modal: the path shows **+11.2%, +23.6% and +39.2%** at successive levels, while each same-parent remainder shows **−0.8%, −0.4% and +0.2%**. Select a row to change the daily curve. Charts come from saved data.

The synthetic strawberry requests rise to +50% over 6–20 July. A smaller Mango × Kowloon rise and a coating decline are also planted. Mango × Kowloon does not receive its own card: the remaining non-strawberry/non-coated branch's best Low sugar split has `p = 0.371859`, so the tree stops there. This is a detector limit, not evidence that the planted rise did not happen.

With Gemini configured, the saved weekly report can include the assistant's investigation and an authored explanation. With an empty key, the native card list and scripted local commands remain available. The assistant's topics are optional. Try a card context change and its Undo if useful; inspect how the cases respond. The stock-versus-space preference changes the calculation, without guaranteeing a measured fulfilment rate. Choose **Review orders**.

## 2. Orders

Inspect grouped cases, supplier order and arrival dates, protection days, forecast range, available and incoming stock, case size, minimum order and any capacity cut. Open a product's order evidence. You can edit a case quantity and Undo it. **Export orders** downloads the CSV from this step. Approve when the displayed quantities are ready; approval queues one persisted replay keyed by the effective order inputs. A later committed case edit prepares a new result.

## 3. Watch

Add a widget for a measure and product scope, optionally with an alert threshold. Inspect its source, move or edit it, then reload to see the server-saved layout. These same widgets continue into Play. Widget edits change the view without rerunning the approved-order simulation. Choose **Next: Play**.

## 4. Play

Play starts automatically once the prepared result is ready. The clock advances in ten-minute steps at fixed 2×, about two seconds per simulated day. Watch stock, deliveries, shortages and the chosen widgets update; the charts redraw hourly. Use **Pause** and **Resume**, then **Replay** if you want another pass. At the final frame, choose **See results** to advance.

## 5. Results

Read the matched-average-space comparison and expand the full comparison. In this designed example, average stock is **36.578548 versus 36.609444 pallets**, a **0.084394%** difference. The plan has **11,160 versus 11,564 short units** (404 fewer), but **89 versus 75 stockout product-days** (14 more) and **HK$68,203.72 versus HK$61,438.78 lost margin** (HK$6,764.94 more). The unchanged rule peaks at **57.986597 pallets**, or **96.64%** of capacity. The selected comparison is the actual approved-order policy; the saved actual result and its final widgets remain available in Results.

The matched comparison selects by measured average-pallet distance within a 2% tolerance, not by shortages. It used three evaluations here. Even the maximum tested explicit service level, 0.98, misses the product-day and lost-margin targets. Do not present this example as an overall policy win or a measured real-world saving. The result and its performance exception are recorded in the [Night 2 ledger](overnight-report.md) and [replay analysis](../reports/n5-replay-analysis.json).

## Quiet week and reset

In sidebar **Settings**, choose **22 June 2026**. It has no cohort cards, though early CUSUM warnings may appear. Return to 27 July for the designed example. Settings reset clears planning progress for the current simulation while retaining synthetic source data and provider allowance. Reloading the app alone preserves saved progress. `python -m scoop.synth.load` intentionally replaces demo tables in the configured database.

The [system design](TECHNICAL_DESIGN.md) explains the model, replay and limits. This is one illustrative synthetic world, not a multi-seed evaluation. The archived 20 July and seed-42 measurements remain in that document for historical context.
