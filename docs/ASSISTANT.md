# Assistant and report

Scoop's live assistant uses **Gemini `gemini-3.8-flash`** to choose validated evidence and planning tools. Forecasts, cohort fitting, order quantities, dashboard persistence and Play remain application calculations. The model writes an explanation; the app draws charts from saved numeric series. It does not accept model-supplied SVG chart code.

## Configuration

The portable `.env.example` selects `SCOOP_LLM_PROVIDER=scripted`, leaves `GEMINI_API_KEY` empty, and sets a US$3 estimated allowance with 120 calls. For live assistance, set `SCOOP_LLM_PROVIDER=gemini` in the ignored local `.env`, provide `GEMINI_API_KEY` in the server process environment, and restart the API. The key is used in the HTTPS `x-goog-api-key` header; it is not returned to the browser, placed in a URL or written to the usage ledger. `SCOOP_GEMINI_MODEL` selects another compatible model without changing the frontend. The local acceptance run's US$20/200-call allowance is not the portable default.

`python -m scoop.prepare_demo` builds the default 20 July plan without a provider call. `python -m scoop.prepare_demo --report` explicitly requests report preparation and may consume allowance when Gemini is configured. The UI can also prepare or retry a weekly review. Opening an already saved report or chat does not repeat its investigation.

## What the live agent sees and can do

The weekly investigation starts from the mechanical scan and saved cohort cards, then can inspect catalog groups, intersections and parent comparisons, operational records and procurement consequences. It saves chosen queries and results, evidence IDs, report claims, questions, model version and usage. The report presents significant and secondary observations with source links; new distinct observations have their own blocks. It may draw a reasonable inference, but an exploratory query is not part of the calibrated detector family and does not prove causation.

The conversation receives the active synthetic plan, compact catalogs, saved query index and recent messages from that plan and stage. It can answer questions, inspect a cohort or order, run a read-only temperature scenario, and apply **explicitly requested** context, objective, case-quantity or dashboard-widget edits. Context rules are optional and recompute derived orders and cards. Edits have Before/After receipts and Undo. The assistant can use the canonical widget tools, so a widget added in chat uses the same server layout as a UI widget and appears in Play.

There is no arbitrary SQL, shell, browser, URL fetch, credential-reading, stage-approval or purchase-confirmation tool. The server checks tool arguments, plan ownership, scope and stage; informational questions and hypotheticals are read-only. The user controls progression from **Report & direction → Orders → Watch & play**. Open discussion topics can remain open when the user continues.

The assistant uses actual tool totals for affected case counts. Progress labels report observable context, provider and tool steps, not hidden reasoning. A success reply follows the database commit. Response details retain tool results and provider identity for review.

## Offline behavior and limits

With an empty key or unavailable provider, the app still offers mechanical cohort cards, a **minimal card-list report**, and a scripted assistant for supported commands. It does not perform autonomous Gemini exploration or produce the same authored report. If a provider fails after an edit tool has already run, the app reports the recorded result rather than running the edit again through the fallback. Failed transactions do not emit success.

The default allowance is 120 provider calls and an estimated US$3 lifetime budget for the local demo. A ledger under ignored `data/cache/` reserves allowance before requests and stores digests and aggregate token counts, not prompts or keys. Unknown transport outcomes retain reservations. The estimates are not billing statements.

The assistant remains a probabilistic writer. Numeric claims should be checked against cited data and edit receipts. Absence of a recorded promotion does not prove a preference shift; a cohort association does not prove causation; forecasted warehouse space and requested service are not guaranteed outcomes. The unmodified 20 July synthetic Play loses 11,528 units under the plan versus 10,191 under the moving-average rule. The P1 null-world and planted-subgroup acceptance checks remain blocked without tuning; see [the work ledger](overnight-report.md) and [algorithm notes](ALGORITHM_NOTES.md).

Provider references: [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) and [generateContent REST API](https://ai.google.dev/api/generate-content).
