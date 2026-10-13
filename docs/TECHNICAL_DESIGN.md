# Scoop: system design and technical document

**Corporate Link Challenge 2026 - working prototype**

Repository: https://github.com/Hcrab/scoop-clc2026
Implementation branch: `claude/scoop-prototype`
Data: deterministic synthetic ice-cream distribution world, seed 42
Team ID, roster and individual contributions: to be supplied and confirmed by the team before submission.

This document follows the subject coverage of the local CLC2026 shortlisting technical-document example and rules v1.6 (2 October 2026). It is a development document, not a declaration that all submission conditions have been met. In particular, repository publication and team declarations remain owner decisions.

## 1. Problem and proposed solution

Cold storage is scarce. A warehouse planner has to replenish familiar products while distinguishing weather-driven demand from persistent changes in preference. A sales increase can also be a promotion, a single large order or a shift in the mix of stores. Treating each increase as permanent can tie up space; ignoring it can cause shortages.

Scoop connects a weekly evidence review to concrete case quantities. The planner sees attribute-level signals, checks explanations, records a purchasing direction, then receives recommendations constrained by supplier calendars, case packs, stock, pipeline and warehouse capacity. A persistent assistant explains the evidence and performs bounded, auditable actions. The core output is a reviewed replenishment plan and watch list.

The prototype represents one DC, 20 stores, four districts, eight suppliers and 60 existing SKUs. All product, customer, order and weather records are synthetic. Its commercial hypotheses require validation on authorised operational data.

## 2. Architecture and data flow

```mermaid
flowchart LR
    S[Synthetic catalog, orders, stock and issued weather] --> D[(PostgreSQL)]
    D --> F[LightGBM demand forecasts]
    D --> C[Weather-adjusted share CUSUM]
    C --> I[Evidence investigator and shift-share]
    F --> R[Calendar-aware replenishment and capacity heuristic]
    I --> P[Weekly plan and human decisions]
    P --> R
    R --> A[FastAPI]
    P --> A
    A <--> U[React planner and scripted assistant]
    U --> W[Purchase confirmation and watches]
    W --> D
    D --> E[Offline baseline evaluation and policy replay]
```

The generation command creates relational source tables. Model runs use time-bounded features; reusable artifacts are cached locally and excluded from version control. Planning combines detector evidence and inventory forecasts, then persists findings, hypotheses, questions, directions and purchase suggestions. The HTTP API returns joined, typed JSON to the UI. Mutations persist choices and decision records. Offline evaluation reads the same source data with explicit training, calibration and replay intervals.

## 3. Data model

| Layer | Main entities | Purpose |
|---|---|---|
| Reference data | Store, Node, Supplier, Product, Nutrition, TagDimension, Tag, ProductTag | Locations, warehouse capacity, calendars, case packs and comparable attributes |
| Daily facts | StoreOrder, NodeInventory, WeatherDaily, WeatherForecast, Promotion, PurchaseOrder | Demand versus fulfilment, stock, information vintages and known commercial events |
| Analytical output | ModelRun, DailyExpectation, CusumSeries | Forecast lineage and signal evidence |
| Decision workflow | Plan, Finding, Hypothesis, Question, Decision, DirectionItem, PurchaseSuggestion, WatchItem, ChatMessage | Human interpretation, recommendations, approvals and context |
| Evaluation only | GroundTruthEvent | Planted scenarios for scoring; not investigator inputs |

The generated world spans June 2024 to August 2026 and contains 986,400 store-SKU-day rows. The default as-of date is 13 July 2026. Reading future rows is permitted only in the offline scorer, never as future actual inputs to a current planning recommendation.

## 4. Technical approach

### Demand and uncertainty

LightGBM models use product/store attributes, calendar features, promotion information and weather available at forecast time. Replenishment needs a demand distribution over a SKU-specific protection interval, not simply a next-day point forecast. The protection interval includes waiting until the ordering weekday, supplier lead time and review interval. Aggregate uncertainty is empirically calibrated; see `docs/ALGORITHM_NOTES.md` for the exact implemented windows and approximations.

### Preference monitoring

The detector compares observed attribute share with expected share after conditioning on ordinary drivers. A frozen baseline avoids immediately absorbing a gradual preference change. CUSUM accumulates departures; bootstrap calibration and multiple-testing rules limit alerts. A statistically interesting group can still reflect promotion, weather or store mix. Shift-share separates descriptive volume, mix and interaction terms.

### Evidence and human judgement

The investigator uses scoped database evidence to rank explanations. Users can classify a finding as persistent, one-off, a data issue, weather-related or uncertain. That judgement changes the direction of relevant purchasing decisions. Persistent and weak evidence are handled differently: an uncertain signal can remain on a watch list without becoming an automatic inventory increase.

### Purchasing

The order-up-to calculation subtracts current stock and pipeline, rounds positive orders to full cases and applies SKU minimum quantities. The chosen margin, fill-rate or sales objective affects recommendation logic. Warehouse space is allocated with a conservative greedy heuristic and SKU-specific pallet footprints. The implementation does not claim global optimality or a guarantee that a requested service parameter equals the observed fill rate.

### Application and assistant

The UI provides Plans, Stores, Catalog and evaluation views. The weekly flow is Discover, Direction, then Execute & watch. A fixed right-hand chat area keeps context visible. FastAPI validates mutations and phase transitions; order confirmation is synthetic and idempotent. The built frontend can be served by the API for a single-origin local demo.

The assistant is a deterministic, explicitly labelled scripted provider. It interprets supported requests against real plan data and records its changes. It performs no remote model calls and no arbitrary SQL or generated HTML execution. The prototype does not require an LLM API key.

## 5. Setup, test and demonstration

See `README.md` for the exact installation and run commands and `docs/DEMO.md` for a guided demonstration. Reproducibility requires PostgreSQL, the pinned Python environment, and the frontend lockfile. Synthetic loading replaces tables in the configured database and is a first-run/reset operation, not a normal startup step.

The demo begins at 13 July 2026. Inspect the weekly report, open a finding's chart and explanation, answer the interpretation questions, approve directions and the objective, inspect the case-level order rationale, confirm one synthetic order, and add a scoped watch. Reload the page to verify persisted decisions. Stores and Catalog provide traceable source context.

## 6. Validation and limitations

The evaluation includes forecast errors against simple baselines, planted-event detection delay, null-world alert behaviour, explanation labels and an inventory replay. Results are generated in `reports/`, with the precise interpretation in `docs/ALGORITHM_NOTES.md`. Missing detections and unfavourable service/inventory trade-offs remain in the report.

The no-trend counterfactual keeps the same catalog, weather and known promotions while removing preference drift, exceptional promotion uplift and bulk orders. It is reproducible for a seed, but changed Poisson intensities mean draws do not remain exactly paired after the first change; it is a detector diagnostic, not a causal estimator.

The final seed-42 run reports these outcomes:

| Measure | Scoop | Comparison / context |
|---|---|---|
| Daily demand WAPE | 49.48% | 28-day average: 52.50%; same weekday: 70.72% |
| Protection-window WAPE | 3.44% | 28-day average: 10.54% |
| Held-out protection interval coverage | 83.33% | 120 windows; nominal 80% |
| Strong trend/district misses | 2 of 7 after BH gate | Raw CUSUM misses 1 of 7 |
| Null-world alarm episodes | 0 after BH gate | 368 raw episodes; one synthetic diagnostic |
| Full policy at 96% parameter | 96.54% fill; 21.9 average pallets | Historical x1.25: 98.72% fill; 32.0 pallets |

The full policy uses less inventory but also achieves lower service than the historical x1.25 policy. This is a trade-off, not a universal performance win. Investigator labels agree with 19 of 25 matched planted-event findings (76%); five unmatched findings are also retained in the report.

The 35 C what-if scenario reuses the demand and capacity pipeline with a temporary temperature override. For the untouched 13 July plan, a 20–26 July override changes proposed cases from 1,282 to 1,898 (+616). It changes neither the saved directions nor confirmed orders.

Final verification passed 23 focused Python tests and the TypeScript/Vite production build. The browser walkthrough reviewed six findings on a separate 6 July plan, approved both stages, changed the water-based factor to 1.10 in Kowloon, set a 96% service objective, confirmed IC023 at 30 cases, added an HK Island fruit-service watch, and verified persistence and CSV export. The 13 July plan remains available for a fresh demonstration.

Application validation covers phase guards, persisted choices, invalid input, idempotent confirmations and as-of views. Frontend compilation and a browser walkthrough provide separate evidence of the usable interaction. A successful build alone is not treated as proof that every flow works.

Important limits are synthetic realism, fixed model windows, approximate aggregated uncertainty, heuristic capacity allocation, no live LLM connection, no real supplier integration and no automatic stock simulation following user confirmations. Deployment authentication, tenancy and production operations are outside this local demonstration.

## 7. AI, data and third-party disclosure

Claude materially contributed the original product discussion, architecture, synthetic data generator and analytical implementation. OpenAI Codex recovered the interrupted work, completed the local application and assisted with review, corrections, verification and documentation. Human team members must review the implementation and supply their own accurate contribution statements. A tool-generated document cannot attest to human contributions.

The runtime data is generated by `scoop.synth.generate`; no sponsor transaction dataset is included. Product names and tags are fixtures. See `docs/THIRD_PARTY.md` for dependencies and installed licence metadata. No external weather API or LLM API is called by the default demo.

## 8. Team and submission readiness

The team must supply its confirmed Team ID, team name, roster, role and specific contribution for each registered member. It must also review AI disclosures, applicable licences and the release contents. The current private branch is not yet the publicly accessible repository required by the competition's shortlisting submission rules.

Before submission, export a reviewed presentation of at most 20 PDF pages and this technical document in PDF, using the competition's Team-ID filename pattern. Verify links and confirm that the publicly accessible release is the intended submitted version. These are publication steps for the owner; this prototype build does not submit anything to the organisers.
