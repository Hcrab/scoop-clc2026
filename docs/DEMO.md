# Demonstration guide

Allow approximately five minutes after the first model build. This is a local, synthetic demonstration. Default clock: **13 July 2026**.

## 1. Orient the planner

Open the app and select the current week. The report should identify its as-of date. Explain that the DC supplies 20 stores with 60 existing products. The user's job is to choose how much to replenish under a warehouse capacity limit.

## 2. Review evidence

Open a reported finding. Compare observed and expected share, the district scope, competing hypotheses and the shift-share explanation. A promotion or a single bulk order should not automatically become a persistent purchasing increase. A weak result can remain uncertain and be watched.

Use the assistant to ask why a finding was raised. Its answer must agree with the visible report. The assistant is explicitly scripted; do not claim a live LLM independently investigated the database.

Try “What if next week is 35 C?” in the discussion. Scoop recomputes the forecast and feasible case quantities without applying the scenario. On the untouched 13 July plan, the result is 1,282 to 1,898 cases (+616). Use “Watch HK Island fruit stockouts” to add a scoped fill-rate watch.

## 3. Record a decision

Answer the interpretation questions using the evidence. Advance to Direction and inspect the resulting `more`, `less`, `hold` or `clear` choices. Change a factor or district scope where appropriate, choose the planning objective, and review the approval summary.

After approval, earlier-stage changes should be blocked. This makes the difference between exploring a plan and approving it visible.

## 4. Inspect a purchase recommendation

In Execute & watch, inspect one SKU's supplier ordering date, protection interval, forecast range, stock position and final number of cases. Explain any capacity cut and the minimum order quantity. Confirm one synthetic purchase order and export the order CSV.

The confirmed line becomes read-only. The API regression test also repeats the identical confirmation and verifies that only one purchase order exists. This does not transmit an order to a supplier or rewrite historical stock snapshots.

## 5. Watch the assumption

Add a fill-rate, days-cover, capacity, delay or tag-share watch with an explicit scope and assumption. Reload the app and verify that the decision, order status, conversation and watch remain present. Browse the relevant store and catalog items for source context.

## 6. Show the evidence and boundaries

Open evaluation results. State the exact synthetic period and baseline, and report both inventory and service outcomes. Use `docs/ALGORITHM_NOTES.md` to explain false alarms, misses and modelling approximations. A requested service level is not a measured service guarantee.

## Reset and repeat

Existing weekly plans are reused so reopening does not erase decisions. Use another supported week for an independent flow. For a complete reset, stop application processes, deliberately rerun `python -m scoop.synth.load` against the isolated demo database, and clear only the generated model cache if the seed or model implementation changed. Loading replaces all demo tables; do not use it as the normal startup command.
