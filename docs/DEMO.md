# Demonstration guide

Allow approximately five minutes after the first model build. This is a local, synthetic demonstration. Seed clock: **13 July 2026**. The delivered walkthrough also contains a completed **20 July 2026** plan and a fresh **27 July 2026** plan; check the date displayed in the app.

## 1. Orient the planner

Open the app and select the current week. The report should identify its as-of date. Explain that the DC supplies 20 stores with 60 existing products. The user's job is to choose how much to replenish under a warehouse capacity limit.

## 2. Review evidence

Choose a finding from the card grid. Compare observed and expected share, the district scope, competing hypotheses and the shift-share explanation. A promotion or concentrated orders should not automatically become a persistent purchasing increase. A weak result can remain uncertain and be watched.

Use the assistant to ask why a finding was raised. Its answer must agree with the visible report. The delivered session uses Gemini through bounded evidence tools. The assistant details show whether a response was live or an offline fallback. It cannot run arbitrary SQL or approve purchases. Do not claim it independently verified causation.

Try “What if next week is 35 C?” in the discussion. Scoop recomputes the forecast and feasible case quantities without applying the scenario. On the 20 July walkthrough after the Water-based persistent interpretation, the observed result was 1,025 to 1,246 cases (+221). Treat this as a recorded example; current quantities depend on saved decisions. Use “Watch HK Island fruit stockouts” to add a scoped fill-rate watch.

## 3. Record a decision

Open Plan discussion from the top-right assistant icon. Its badge counts open discussion topics. Discuss the evidence and record interpretations when useful; the assistant maintains a structured list of open and resolved topics. Select Continue to move to Direction. Topics remain available across stages, and advancing does not pretend to answer them.

Inspect the resulting `more`, `less`, `hold` or `clear` choices. Change the percentage to buy more or less, or its district scope where appropriate, choose the planning objective, and review the approval summary and watch selection. Baseline watches cover service, shortages, excess cover, projected space and late suppliers.

After approval, earlier-stage changes should be blocked. This makes the difference between exploring a plan and approving it visible.

## 4. Inspect a purchase recommendation

In Execute & watch, inspect one SKU's supplier ordering date, protection interval, forecast range, stock position and final number of cases. Explain any capacity cut and the minimum order quantity. Confirm one synthetic purchase order and export the order CSV.

The confirmed line becomes read-only. The API regression test also repeats the identical confirmation and verifies that only one purchase order exists. This does not transmit an order to a supplier or rewrite historical stock snapshots.

## 5. Watch the assumption

Add a fill-rate, days-cover, capacity, delay or tag-share watch with an explicit scope and assumption. Reload the app and verify that the decision, order status, conversation and watch remain present. Browse the relevant store and catalog items for source context. Prepare the following week to see carried assumptions and the previous-week recap. Prior approval snapshots remain unchanged when a later watch is edited.

## 6. Show the evidence and boundaries

Open evaluation results. State the exact synthetic period and baseline, and report both inventory and service outcomes. Use `docs/ALGORITHM_NOTES.md` to explain false alarms, misses and modelling approximations. A requested service level is not a measured service guarantee.

## Reset and repeat

Open Settings in the sidebar. Choose a simulation scenario and week, then apply it. Existing plans in that simulation are reused. Switching between simulation worlds preserves each world's progress, with separate source data and model caches.

Reset in Settings clears planning progress for the current simulation and prepares a fresh week. Its confirmation explains the affected records. Other simulations and the assistant allowance are retained. The generator command in the installation instructions is a first-setup operation, not the normal repeat-demo workflow.

## Saved walkthrough in the local delivery

- The original simulation's clock is July 27. Its newest plan starts in Discover with six discussion topics.
- July 20 remains available in Plan history at Execute & watch. It uses a 96% service preference and a Water-based +10% direction limited to Kowloon.
- Dragon Fruit Smoothie Cup was recommended at 25 cases and manually confirmed at 26. Its detail panel and saved real-model answer distinguish those quantities.
- The Fruit/HK Island watch was edited during Execute. Its approved Direction copy retains the original wording; the current version carries to July 27.
- July 27's prior-week recap shows one confirmed purchase and 26 cases, using observations through July 26. It does not claim the demonstration purchase caused the observed service result.
- Local launchers accept either live or offline assistant health; provider choice does not make an already-running server appear unavailable.
