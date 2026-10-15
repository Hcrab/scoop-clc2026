# Demonstration guide

This walkthrough uses the designed synthetic seed-93 world: 75 products, 20 stores, four districts, one distribution centre, eight suppliers and a 66-pallet cold store. The source has 1,233,000 store-SKU-day rows. The public plan opens on **27 July 2026** (`P20260727`). First-plan preparation may take several minutes. The app does not place real supplier orders.

## 1. Report

Read the weekly report and open the first change card, **Strawberry → Value price → Water-based**. Its four products are IC006, IC061, IC062 and IC063. The estimated change is **+38.1552%**, with an 80% interval of **+35.1210% to +41.2575%**. Expand the card's right-side tree or its evidence modal: the path shows **+11.2%, +23.6% and +39.2%** at successive levels, while each same-parent remainder shows **−0.8%, −0.4% and +0.2%**. Select a row to change the daily curve. Charts come from saved data.

The synthetic strawberry requests rise to +50% over 6–20 July. A smaller Mango × Kowloon rise and a coating decline are also planted. Mango × Kowloon does not receive its own card: the remaining non-strawberry/non-coated branch's best Low sugar split has `p = 0.371859`, so the tree stops there. This is a detector limit, not evidence that the planted rise did not happen.

With Gemini configured, the saved weekly report can include the assistant's investigation and an authored explanation. With an empty key, the native card list and scripted local commands remain available. The assistant's topics are optional. Each change card puts one estimated-demand effect up front; raw 14-day and fill context is quieter. The left action rows focus their matching cards without showing quantities. Try a card context change and its Undo if useful. In the right column's **This week's direction**, move the in-stock target toward **Save space** or **Avoid stockouts**. Check the live, read-only preview of cases and whole-warehouse peak; **Apply** commits the choice and **Reset to auto** restores automatic targets. An amber inherited-excess line appears if existing arrivals warrant it. The control changes the calculation without guaranteeing a measured fulfilment rate. On desktop, the two columns scroll separately; on a narrow screen they stack. Choose **Review orders**.

## 2. Orders

Inspect grouped cases, supplier order and arrival dates, protection days, forecast range, available and incoming stock, case size, minimum order and any capacity cut. Open a product's order evidence. You can edit a case quantity and Undo it. **Export orders** downloads the CSV from this step. Approve when the displayed quantities are ready; approval queues one persisted replay keyed by the effective order inputs. A later committed case edit prepares a new result.

## 3. Watch

Add a widget for a measure and product scope, optionally with an alert threshold. Inspect its source, move or edit it, then reload to see the server-saved layout. These same widgets continue into Play. Widget edits change the view without rerunning the approved-order simulation. Choose **Next: Play**.

## 4. Play

Play starts automatically once the prepared result is ready. The clock advances in ten-minute steps at fixed 2×, about two seconds per simulated day. **Today so far** accumulates requests and losses during the current day; completed daily lines settle at 23:50, while the current day has its own hollow point. Dispatch stays pending until 18:00. Watch stock, deliveries, shortages and the chosen widgets update every ten simulated minutes. Use **Pause** and **Resume**, then **Replay** if you want another pass. At the final frame, choose **See results** to advance.

## 5. Results

Read the three whole-warehouse outcomes against the unchanged moving-average rule under the same 66-pallet cold-store capacity. In this designed example, the plan has **11,160 versus 11,564 short units** (404 avoided), **89 versus 75 stockout product-days** (14 extra) and **HK$68,203.72 versus HK$61,438.78 lost margin** (HK$6,764.94 extra). The adverse differences appear in red. Average closing stock is **36.864173 versus 36.609444 pallets**. Both replay peaks are **57.986597 pallets**, with zero days over capacity; the starting projected peak was **61.304557 pallets**, or **92.8857%** of capacity. The approved-order outcome and its final widgets remain available in Results.

The 16-day result avoids some short units while losing more product-days and margin. The [five-SKU diagnosis](reports/night3-m1.md) traces the adverse outcome to smaller first orders and lead-time coverage, with no first-week capacity cuts or deferred default receipts. Present this as an accepted diagnosis, not an overall policy win or a measured real-world saving. The [work ledger](overnight-report.md) records the broader evidence.

## Quiet week and reset

In sidebar **Settings**, choose **22 June 2026**. It has no cohort cards, though early CUSUM warnings may appear. Return to 27 July for the designed example. Reset restores that prepared week's persisted initial report, orders and default widgets, clearing edits, context, chat, replay and progression. A same-world reset reuses small saved plan records without rebuilding source data or model fits or calling Gemini; measured API resets took 174, 85 and 94 ms, with a usable report in 1.404 s. A first unprepared week still needs preparation. Reloading alone preserves progress. `python -m scoop.synth.load` intentionally replaces demo tables in the configured database.

The [system design](TECHNICAL_DESIGN.md) explains the model, replay and limits. This is one illustrative synthetic world, not a multi-seed evaluation. The archived 20 July and seed-42 measurements remain in that document for historical context.
