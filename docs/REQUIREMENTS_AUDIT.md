# Product requirements and verification map

This map follows the accepted project scope and subsequent refinement request. Superseded ideas such as new-product selection and retail shelf allocation are outside this prototype. The private source conversation is not included in the repository.

| User outcome | Implementation | Verification / remaining boundary |
|---|---|---|
| Replenish familiar products at one warehouse | Synthetic source world, existing-product catalog, supplier calendars and case quantities | 20 stores, 60 products, eight suppliers; source data is synthetic |
| One weekly plan, with current work easy to find | Default current week; history and demo date are secondary controls | Actual browser review; existing plans preserved |
| Understand a change before deciding | Directly visible finding cards, observed/expected demand, explanations and contextual discussion | Explicit interpretation changes persist and recompute purchases |
| Keep technical implementation out of the primary flow | Percent changes, product names, dates, quantities and next actions; calculations in disclosures | Apple HIG Writing/Layout/Accessibility informed the review; this is a web app with its own visual identity |
| Discuss the selected finding and track open topics | Assistant icon count, structured conversational agenda, plan/stage/finding context and decision history | Topic persistence is separate from buying decisions and does not block Continue |
| Explore different demonstrations | Sidebar Settings with simulation data, week selection and scoped reset | Switching preserves other simulation progress; data/model caches stay aligned |
| Use a real assistant on more than canned questions | Gemini, bounded domain tools and real progress events | Real Chinese responses reviewed; probabilistic prose still needs human judgement |
| Explain / classify / test 35°C / add a district fruit watch | Evidence lookup, shared interpretation handler, read-only scenario, validated watch tools | Mocked failure regressions plus real-provider demonstration records; scenario never changes orders |
| Control the service/stock tradeoff | Profit, service and sales objectives; category/product/district adjustments | Invalid scopes and approved-stage changes rejected; requested service is not a guaranteed achieved fill rate |
| Review assumptions before execution | Five baseline measures and decision-derived watches; approval stores the reviewed selection | Idempotent approval; later edits keep the original approval snapshot |
| Follow the week without rebuilding history | Watch edits/archives, carryover provenance and prior-week recap | Reopening is stable; archived items stay archived; no claim that confirmed demo orders changed historical stock |
| Keep model and monitoring versions coherent | Monthly frozen model versions, past-only training/calibration, monitoring reset and direction retirement | Monthly regression tests and rolling-origin evaluation; old saved plans retain their recorded findings |
| Use statistics as evidence, not an answer key | CUSUM/BH, shift-share and scoped investigation; bounded weak reviews | Planted labels are evaluation-only; missed/late detections and false alarms are reported |
| Turn choices into reviewable purchasing records | Whole-case recommendations, inventory/pipeline rationale, confirmation and CSV export | Confirmation is idempotent and checked against dated capacity; no external supplier transmission |
| Remain usable when a model call fails | Explicit offline fallback, bounded allowance, transactional changes, durable tool evidence | Provider failures, duplicate intent, scope, rollback and concurrent allowance regressions |
| Have a presentable handoff | Technical document, demo guide, editable 12-slide deck, figures and local launcher | Final artifacts are visually reviewed; team identity and competition submission remain to be confirmed by the owner |

## Boundaries that must remain visible

- No authorised real retailer data or live warehouse pilot has been used. There is no measured production saving or planner usability study.
- Historical inventory is a generated record; local purchase confirmations do not simulate a new physical warehouse trajectory.
- The dated capacity allocator is a heuristic. Forecast uncertainty transfer and the timing of statistically gated alerts have measurable weaknesses.
- Gemini can phrase an interpretation too confidently. Numeric calculations and actions come from tools; expandable evidence and human approval remain necessary.
- The local app is a single-user prototype. A production pilot still needs authentication, operational integration, observability and agreed ownership.
