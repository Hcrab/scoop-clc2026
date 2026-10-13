# Plan discussion

The live assistant uses Gemini to interpret a question and choose from a small set of validated planning tools. Forecasting, quantity calculations, scope checks and database changes remain in Python. The offline assistant uses the same mutation tools for its supported commands.

## Local configuration

Set `SCOOP_LLM_PROVIDER=gemini` in the ignored local `.env`. Supply `GEMINI_API_KEY` in the server process environment. The key is used only in the HTTPS `x-goog-api-key` request header to Google's Gemini endpoint; it is not returned to the browser, included in URLs, or written to the usage ledger. `scripted` remains the portable default in `.env.example`.

The selected model is `gemini-3.8-flash`, verified against the authenticated model listing on 14 October 2026. The implementation uses the supported `generateContent` REST API and function declarations. A model can be changed through `SCOOP_GEMINI_MODEL` without changing frontend code. Provider availability is checked through actual requests; configuration alone does not prove that a remote service is healthy.

## Data and actions

Each request receives the active synthetic plan, compact category/product catalogs, and up to eight recent messages from that same plan and stage. It can inspect a finding, a purchase recommendation or a scoped historical measure, and run a temperature scenario. It can record an explicitly requested interpretation, goal, buying direction or watch. There is no SQL, shell, browser, arbitrary URL, credential-reading, stage-approval or purchase-confirmation tool.

Both provider instructions and server-side intent checks keep informational questions and hypotheticals read-only. The server validates tool arguments, plan ownership, product/district scope and the current stage. A calculation scenario never changes saved directions or orders. Ambiguous or unsupported actions should be clarified rather than guessed.

The browser streams actual progress labels for context loading, provider requests and tool execution. These labels describe observable operations; they are not hidden model reasoning. The final success response is sent only after the transaction commits. Tool results and the provider used are saved with the assistant message under expandable response details.

## Failure behavior and allowance

The default allowance is 120 provider calls and a conservative estimated US$3 total across this local demo's lifetime. A chat turn may use up to four calls. A SQLite ledger under ignored `data/cache/` reserves allowance atomically before each request. It stores request digests and aggregate input/output counts, including thinking tokens, but no prompt text or key. Unknown transport outcomes retain their reservation. Estimates use US$1.50 per million input tokens and US$7.50 per million output tokens, deliberately above the verified standard rate; these estimates are not a billing statement.

If the provider cannot start, the response explicitly identifies the offline demo fallback. If an explanation fails after a tool has already run, the assistant summarizes those recorded tool results and does not rerun the mutation through the fallback. Invalid stages/scopes roll back; a failed database transaction never emits a success event. A single local live request runs at a time to avoid accidental parallel actions and uncontrolled spend.

## Interpretation limits

The assistant is still a probabilistic writer. Its numeric answers must come from context or tools; tool evidence is available for review. Absence of a recorded promotion does not prove a preference shift, a mix decomposition does not identify customers who switched, and observed warehouse space is not a guarantee about future arrivals. Historical service measurements are separate from forecasts and cannot prove the effect of a confirmed demo order. These limits are explicit in the prompt and real-response review; they are not a claim that hallucination is impossible.

Provider documentation: [Function calling](https://ai.google.dev/gemini-api/docs/function-calling), [generateContent REST API](https://ai.google.dev/api/generate-content), [pricing](https://ai.google.dev/gemini-api/docs/pricing).
