# Demonstration guide

This walkthrough uses the designed synthetic seed-93 world: 75 products, 20 stores, four districts, one distribution centre, eight suppliers and a 66-pallet cold store. The source has 1,233,000 store-SKU-day rows. The public plan opens on **27 July 2026** (`P20260727`). First-plan preparation may take several minutes. The app does not place real supplier orders.

## 1. Report

Read the weekly report and open the first change card, **Strawberry → Value price → Water-based**. Its four products are IC006, IC061, IC062 and IC063. The estimated change is **+38.1552%**, with an 80% interval of **+35.1210% to +41.2575%**. Expand the card's right-side tree or its evidence modal: the path shows **+11.2%, +23.6% and +39.2%** at successive levels, while each same-parent remainder shows **−0.8%, −0.4% and +0.2%**. Select a row to change the daily curve. Charts come from saved data.

The synthetic strawberry requests rise to +50% over 6–20 July. A smaller Mango × Kowloon rise and a coating decline are also planted. The heat episode spans **30 July–2 August**, starting three days after the order and ending inside the seven-day skill window of the forecast issued **26 July**. Its temperatures are 33.6, 33.4, 33.8 and 33.6°C; source history before 30 July is unchanged. Mango × Kowloon does not receive its own card: the remaining non-strawberry/non-coated branch's best Low sugar split has `p = 0.371859`, so the tree stops there. This is a detector limit, not evidence that the planted rise did not happen.

With Gemini configured, the saved weekly report can include the assistant's investigation and an authored explanation. With an empty key, the native card list and scripted local commands remain available. The assistant's topics are optional. Each change card puts one estimated-demand effect up front; raw 14-day and fill context is quieter. The left action rows focus their matching cards without showing quantities. Try a card context change and its Undo if useful. In the right column's **This week's direction**, move the in-stock target toward **Save space** or **Avoid stockouts**. Check the live, read-only preview of cases and whole-warehouse peak; **Apply** commits the choice and **Reset to auto** restores automatic targets. An amber inherited-excess line appears if existing arrivals warrant it. The control changes the calculation without guaranteeing a measured fulfilment rate. On desktop, the two columns scroll separately; on a narrow screen they stack. Choose **Review orders**.

## 2. Orders

Inspect grouped cases, supplier order and arrival dates, protection days, forecast range, available and incoming stock, case size, minimum order and any capacity cut. The default has 2,172 initial cases. Open a product's order evidence. You can edit a case quantity and Undo it. **Export orders** downloads the CSV from this step. Approve when the displayed quantities are ready; approval queues one persisted replay keyed by the effective order inputs. A later committed case edit prepares a new result.

## 3. Watch

Start with warehouse health for the **14 days before the order**. Open **Low cover** to see products whose recent demand may exhaust stock before their next arrival. Add a widget for a measure and product scope, optionally with an alert threshold. It plots one measure: recorded values in grey, then the Scoop plan in green after the order marker, with no rule overlay or benchmark band. Inspect its source, move or edit it, then reload to see the server-saved layout. These same widgets continue into Play. Widget edits change the view without rerunning the approved-order simulation. Choose **Next: Play**.

## 4. Play

Play starts automatically once the prepared result is ready. The clock advances in ten-minute steps at fixed 2×, about two seconds per simulated day. The clock shows a timestamp such as **Wed 29 Jul · 00:50** and **Day 3 since the order**. Warehouse health now covers flows **since 27 July**; low cover follows the remaining stock and next known arrival. Requests and losses accumulate during the current day. Completed daily points connect at the 23:50 close; from noon the unfinished day appears separately as a hollow **Projected full day** point. Watch stock, deliveries, shortages and the chosen widgets update every ten simulated minutes. In **What happened**, expand an order to see its product lines; there is no separate Decision entry. Use **Pause** and **Resume**, then **Replay** if you want another pass. At the final frame, choose **See results** to advance.

## 5. Results

Read the three whole-warehouse outcomes against the unchanged moving-average rule under the same 66-pallet cold-store capacity. The [measured default replay](../reports/d4-replay-measurement.json) has **6,347 versus 6,063 short units** (284 extra for Scoop), **52 versus 39 stockout product-days** (13 extra) and **HK$38,125.69 versus HK$30,849.11 lost margin** (HK$7,276.58 extra). All three differences are adverse and appear as losses. Average closing inventory is **37.974486 versus 37.755089 pallets**. Both policies peak at **57.986597 pallets** with zero days over capacity. The closing-stock chart puts recorded history in grey, Scoop in green and the Simple rule in orange on one shared axis. The approved-order outcome and its final widgets remain available in Results.

The order target uses a one-sided correction fitted at each product's economic critical ratio or selected service target; the displayed central forecast interval stays unchanged. The frozen 478-window calibration set covers its upper target 96.44% before and 97.07% after correction. In a separate strict rolling-origin check, coverage stays 96.44% before and after; the fitted calibration-set figure is not an independent performance gain. See the [mid-course protocol](reports/day16-midcourse-protocol.md) for the evidence boundary. Present the Results as one illustrative synthetic outcome that underperforms the rule on all three primary outcomes, not a measured real-world saving.

## Quiet week and reset

In sidebar **Settings**, choose **22 June 2026**. It has no cohort cards, though early CUSUM warnings may appear. Return to 27 July for the designed example. Reset restores that prepared week's persisted initial report, orders and default widgets, clearing edits, context, chat, replay and progression. A same-world reset reuses small saved plan records without rebuilding source data or model fits or calling Gemini; measured API resets took 174, 85 and 94 ms, with a usable report in 1.404 s. A first unprepared week still needs preparation. Reloading alone preserves progress. `python -m scoop.synth.load` intentionally replaces demo tables in the configured database.

The [system design](TECHNICAL_DESIGN.md) explains the model, replay and limits. This is one illustrative synthetic world, not a multi-seed evaluation. The archived 20 July and seed-42 measurements remain in that document for historical context.
