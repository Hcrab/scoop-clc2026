# Plan discussion

The live assistant uses Gemini to interpret a question and choose from a small set of validated planning tools. Forecasting, quantity calculations, scope checks and database changes remain in Python. The offline assistant uses the same mutation tools for its supported commands.

## Local configuration

Set `SCOOP_LLM_PROVIDER=gemini` in the ignored local `.env`. Supply `GEMINI_API_KEY` in the server process environment. The key is used only in the HTTPS `x-goog-api-key` request header to Google's Gemini endpoint; it is not returned to the browser, included in URLs, or written to the usage ledger. `scripted` remains the portable default in `.env.example`.

The selected model is `gemini-4-argon`. Its official model documentation and an actual authenticated `generateContent` response were verified on 14 October 2026. The implementation uses REST function declarations and preserves opaque thought signatures within the tool loop. A model can be changed through `SCOOP_GEMINI_MODEL` without changing frontend code. Configuration alone does not prove provider availability.

## Data and actions

Each request receives the active synthetic plan, compact category/product catalogs, and up to eight recent messages from that same plan and stage. It can inspect a finding, a purchase recommendation or a scoped historical measure, and run a temperature scenario. It can record an explicitly requested interpretation, goal, buying direction or watch. There is no SQL, shell, browser, arbitrary URL, credential-reading, stage-approval or purchase-confirmation tool.

Both provider instructions and server-side intent checks keep informational questions and hypotheticals read-only. The server validates tool arguments, plan ownership, product/district scope and the current stage. A calculation scenario never changes saved directions or orders. Ambiguous or unsupported actions should be clarified rather than guessed.

The browser streams actual progress labels for context loading, provider requests and tool execution. These labels describe observable operations; they are not hidden model reasoning. The final success response is sent only after the transaction commits. Tool results and the provider used are saved with the assistant message under expandable response details.

## Weekly exploration and conversation

After a new plan's mechanical scan, the live agent chooses additional read-only queries before submitting an integrated weekly report with an AI-authored title, HTML/CSS, charts and interactive evidence. Existing plans offer Explore this week. Completed reports are reused; GET requests and opening the conversation do not spend provider calls. A failed or offline review leaves the mechanical plan available and supports retry.

The agent can list catalog groups, query intersections and parent comparisons, inspect operational records, and preview procurement consequences using the existing algorithms. The agent chooses query arguments and follow-ups from returned evidence. The saved review includes query arguments/results, evidence IDs, claims, questions, model version and usage. Query IDs referenced by claims must exist. This is exploratory investigation, not an extension of the calibrated mechanical FDR family or proof of causation.

The conversation opens with observations and specific numbered business questions, followed by normal text input. The report and query evidence are available to subsequent chat turns. Questions that require local knowledge or a purchasing choice remain explicit; a numerical result alone is not human authorization to change an order.

The assistant maintains question state in the plan, exposed as `discussion.items` and `discussion.open_count`. A completed review replaces untouched mechanical prompts with its actual questions. During conversation, the assistant can add a relevant follow-up, resolve a question after addressing it, or reopen it. The top-right assistant badge reads this saved state.

Agenda updates are advisory metadata. They do not approve stages, classify a finding, change a buying direction or confirm a purchase. Those business actions keep their own validated tools and explicit intent rules. An explicit finding interpretation also resolves its related discussion topic. Merely continuing to another stage leaves open topics open and preserves unanswered question records.

The human controls Continue. Discussion progress is kept independently of the stage transition; it is not an approval prerequisite.

## Failure behavior and allowance

The default allowance is 120 provider calls and a conservative estimated US$3 total across this local demo's lifetime. Chat uses up to four calls; weekly exploration uses up to seven rounds and twelve additional queries. A SQLite ledger under ignored `data/cache/` reserves allowance atomically before each request, including that request's actual output cap. It stores digests and aggregate token counts including thinking, but no prompt text or key. Unknown transport outcomes retain reservations. Gemini 4 estimates use conservative US$4/20 per million input/output tokens (the documented post-introductory rates); other models retain the previous US$1.50/7.50 estimate. These estimates are not a billing statement.

If the provider cannot start, the response explicitly identifies the offline demo fallback. If an explanation fails after a tool has already run, the assistant summarizes those recorded tool results and does not rerun the mutation through the fallback. Invalid stages/scopes roll back; a failed database transaction never emits a success event. A single local live request runs at a time to avoid accidental parallel actions and uncontrolled spend.

## Interpretation limits

The assistant is still a probabilistic writer. Its numeric answers must come from context or tools; tool evidence is available for review. Absence of a recorded promotion does not prove a preference shift, a mix decomposition does not identify customers who switched, and observed warehouse space is not a guarantee about future arrivals. Historical service measurements are separate from forecasts and cannot prove the effect of a confirmed demo order. These limits are explicit in the prompt and real-response review; they are not a claim that hallucination is impossible.

Provider documentation: [Gemini 4 Argon](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon), [migration and pricing](https://ai.google.dev/gemini-api/docs/latest-model), [Function calling](https://ai.google.dev/gemini-api/docs/function-calling), [generateContent REST API](https://ai.google.dev/api/generate-content).

Discover separates AI report from Trend explorer. Programmatic single-attribute and combination results remain accessible without AI and are supplied to the report agent as saved T-prefixed evidence, separately from its additional query allowance. Distinct new observations receive their own illustrated report blocks; layout guidance remains advisory, with no sentence-style gate. Generated HTML runs in an isolated report frame with source links to saved evidence. See AI_REPORTS.md.
