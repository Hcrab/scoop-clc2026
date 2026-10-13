# Scoop presentation copy

Working copy for a 12-page shortlisting deck, following the topics in the official example. This is editable copy, not a finished competition submission. Add the team's verified identity before export. Use actual application screenshots and generated evaluation charts rather than invented mock evidence.

## 1. Scoop

**Planning the next cold-store order**

Corporate Link Challenge 2026

Speaker note: Introduce the registered team using confirmed names and Team ID. Scoop is a local prototype based on synthetic data. Its focus is the replenishment of existing ice-cream products.

## 2. A change in demand needs a purchasing decision

Warehouse planners need to decide which products deserve scarce freezer space.

Scoop connects demand forecasts and preference signals to a reviewed weekly order plan.

The intended value is fewer unexplained purchasing decisions, with service and inventory trade-offs visible before approval.

Visual: one clear screenshot of the weekly report.

Speaker note: The value proposition is a hypothesis to validate with planners. Do not claim measured time or cost savings in a real operation.

## 3. More sales can mean several different things

A hot week, a promotion, a bulk order and a lasting preference change can all increase demand.

Treating each one as permanent risks excess stock. Ignoring a persistent change risks shortages.

Scoop's target user is the DC replenishment planner. Success means useful explanations and a defensible service/inventory trade-off.

Visual: four short examples from the synthetic findings with their actual evidence.

## 4. The planner reviews, decides and orders

**Discover:** inspect a signal and competing explanations.

**Direction:** approve what to buy more or less of, and where.

**Execute & watch:** inspect case quantities, confirm an order and monitor the assumptions.

Speaker note: The system records human judgement. A weak statistical signal need not become an automatic purchase.

## 5. A reproducible synthetic distribution world

1 cold store. 20 stores. 60 products. 8 suppliers.

986,400 store-SKU-day demand records from June 2024 to August 2026.

The data includes stock, shipped quantities, promotions and weather forecast vintages. Seed 42 makes the demonstration reproducible.

Speaker note: All operational records are synthetic. The planted events provide evaluation labels, not real market observations or investigator inputs.

## 6. Evidence stays beside the decision

The report shows observed versus expected share and alternative explanations.

The direction board records scope and how much more or less to buy.

Order rationale connects the approved direction to supplier dates, stock position and cases.

Visual: a large report screenshot and a focused crop of the actual order rationale.

## 7. A small, inspectable architecture

PostgreSQL stores the source data and decisions.

Python analytics produce forecasts, share alerts and replenishment recommendations.

FastAPI connects the React planner and bounded assistant to persisted state.

Visual: the architecture in `TECHNICAL_DESIGN.md`, simplified to readable components.

Speaker note: The repository default runs offline. The delivered session also exercises Gemini 3.8 Flash through validated tools, with visible live/fallback status and a usage allowance.

## 8. Each method answers a different question

LightGBM: how much demand should the protection interval contain?

CUSUM: is attribute share departing persistently from expectation?

Shift-share: how much change comes from volume, mix or interaction?

Replenishment heuristic: which feasible case quantities fit the objective and available space?

Speaker note: Explain the information cutoff, uncertainty approximation and heuristic capacity assumptions. These methods are not interchangeable, and descriptive attribution is not causal proof.

## 9. One complete workflow

Use the separate 20 July 2026 walkthrough, preserving the earlier saved plans.

Inspect a finding, choose an interpretation and approve a purchasing direction.

Review and confirm a synthetic order, then add a scoped watch. Reload to show that the decisions persist.

Visual: three actual screenshots of the same plan progressing through the workflow.

Speaker note: Show a real case quantity and repeat the confirmation to demonstrate idempotency. No order is sent to a supplier.

## 10. The results include the trade-offs

Compare forecast WAPE and interval coverage with simple baselines.

Report detection delays, missed events and false alarms in the no-trend counterfactual.

Compare replay fill rate with inventory and peak capacity usage.

Visual: charts generated directly from `reports/evaluation.json`, with the exact period and units. Final run: rolling protection WAPE 10.85% versus 10.04%; coverage 64.49% over 780 windows. Full policy at 96%: 98.58% fill and 29.0 average pallets; historical x1.25: 98.72% and 32.0. Report both sides of this trade-off.

Speaker note: Higher service can require more stock. A conservative capacity policy can lower service. A synthetic result is evidence about this implementation, not proof of business savings.

## 11. The next test is with real planning decisions

Near term: obtain authorised data, validate the schema and review explanations with a planner.

Then: compare recommendations in shadow mode, calibrate uncertainty and choose service/capacity targets.

Before deployment: approve data use, implement access control and operational monitoring, and validate live LLM behaviour on authorised operational data.

Speaker note: Keep the roadmap conditional on data permission and user feedback. The current stock view is historical; a full interactive inventory simulator and supplier integration remain future work.

## 12. A reviewed order, with a reason

Scoop makes the evidence, human judgement and purchasing consequence visible in one workflow.

Repository: https://github.com/Hcrab/scoop-clc2026

Speaker note: Add the team's verified names, roles, contributions and contact details. The current repository is private; publish a reviewed release before using a public-repository claim in the final deck. Local demo access is not an online judging URL.
