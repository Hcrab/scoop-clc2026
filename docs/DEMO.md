# Demonstration guide

This walkthrough uses the public synthetic seed 93, with **75 products**, **20 stores**, one distribution centre, eight suppliers and a **71-pallet** cold store. A fresh setup opens the week of **20 July 2026**. Allow several minutes for first-plan preparation. The app does not place real supplier orders.

## 1. Report & direction

Open the 20 July plan. The first cohort card is the broad **Water-based** group, not a separate strawberry-only first card. Inspect its evidence and the report's own source links. The report may separately discuss strawberry demand, but that editorial observation is not a claimed isolated detector split. Expand a card to see actual and expected trends and its query evidence. Charts are drawn by the app from saved data.

Open the assistant from the top-right entry to discuss its numbered questions. With Gemini configured, the weekly report includes the agent's additional saved queries and an authored explanation. With an empty key, expect a minimal card list and a scripted assistant with a small command vocabulary. Offline operation does not reproduce autonomous investigation.

Use a card's context controls to try a one-off change, end date, posterior cap or expectation prior. Check the recomputed factor and case effect, then use the edit receipt's **Undo** if this was only a demonstration. Context changes are optional; they can be made in later stages and return the plan to the appropriate decision view. Adjust **Fewer stockouts ⟷ Less space**. The preference changes the calculation; it is not a guaranteed measured fill rate. Select **Review orders** when ready.

## 2. Orders

Inspect the grouped order list and its capacity summary. Open a product's order evidence for the supplier order and arrival dates, protection days, forecast range, available and incoming stock, case size, minimum order and any capacity cut. Edit a final case quantity, inspect Before/After and Undo, then approve the orders. There is no separate watch approval step.

For a concrete arrival, the unmodified default has **IC006 / Strawberry Burst Bar: 45 cases ordered 20 July, four-day lead, arriving 24 July**. The replay receives its 1,800 units on day 5. This is a synthetic plan calculation, not a real inbound delivery.

## 3. Watch & play

Open **Dashboard** and add a widget for a measure, scope and optional alert threshold. Check its source data, move it to a new position, reload to see the server-saved order, and remove or Undo it. The same canonical widget definitions appear during Play.

Open **Purchases** to confirm one synthetic line or export CSV. Confirmed demo purchases are local records and do not rewrite historical stock. Open **Play** and run the proposed orders against the moving-average rule. Its default horizon is the longest positive ordered supplier lead plus seven days, limited to 21 days and the available calendar. On this default plan it covers **20 July through 4 August (16 days)**. The replay shows both policies on the same widgets, decision-linked events, and then three affected-product outcome numbers: units saved, average pallet difference and stockout product-days avoided. Expand the full comparison for affected products and the whole warehouse.

The unmodified 20 July run is adverse to the plan on lost units: **11,528** versus **10,191** for the rule. Average pallets are **36.6402** versus **44.6169**; peak pallets are **49.9550** versus **65.4033**. The rule's peak is 92.1% of the 71-pallet capacity in this selected window. Do not describe this as an overall policy win or as a measured real-world saving.

## 4. Quiet week and reset

In sidebar **Settings**, choose **22 June 2026** and apply. Its production cohort fit has **zero cards**, although four CUSUM early warnings can still appear. Return to 20 July. Settings reset clears planning progress for the current simulation, including context overrides, while retaining synthetic source data and provider allowance. Reloading the app alone preserves saved plans. The `python -m scoop.synth.load` command is for first setup or an intentional full data replacement.

## Evidence to cite

The measured default and quiet weeks, arrival timing and policy comparison are recorded in [the work ledger](overnight-report.md) and `reports/p6-play-final.json` / `reports/p6-week-evaluation.json`. The corrected P1 null-world test has 4 root splits in 34 weeks, exceeding the maximum of 3. The default week also does not isolate the planted strawberry four as the first card. No statistical threshold or other algorithm parameter was tuned to make those checks pass. This synthetic demonstration does not establish retail savings.
