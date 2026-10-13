# Product and modelling decisions

This record describes the local prototype. The synthetic world and replay are evidence about this implementation, not evidence of commercial impact at PARKnSHOP or LOGFLOWS.

## 1. Scope: a cold-store planner

Scoop chooses replenishment quantities for existing ice-cream SKUs at one distribution centre. It serves 20 fictional stores in four Hong Kong districts, with 60 fictional products and eight suppliers. It does not choose new listings or allocate retail shelf space. Store orders represent observed demand; shipped quantities measure fulfilment and must not silently replace demand when stockouts occur.

The warehouse capacity is expressed in pallets. Each SKU has units per case, cases per pallet, a minimum order quantity, a supplier ordering weekday and a lead time. A case cannot be treated as a uniform amount of warehouse space across products.

## 2. Product flow and human decisions

A weekly plan moves through **Discover -> Direction -> Execute & watch**. The planner examines evidence and alternative explanations, decides which changes to treat as persistent, then approves a direction and an operational objective. The backend persists those choices, order confirmations and chat messages. Earlier stages become read-only after approval. Reopening a plan must reuse its decisions rather than rebuilding it destructively.

Directions are `more`, `less`, `hold` or `clear`. They concern existing stock, have explicit factors and district scopes, and remain visible to the user. Weak signals should lead to a watch rather than a confident claim of a trend.

The interface expresses changes as percentages and business choices. Before strategy approval, the planner reviews the proposed watch list. Approval freezes the selected assumptions and dated capacity projection. Later edits have their own decision records. Unfinished watches carry into the next week; the recap separates historical facts from recorded purchasing choices.

## 3. Product attributes

Tags include single-choice, multiple-choice, graded and numeric dimensions. Dairy content, richness and sweetness are graded values. Price and nutrition produce numeric dimensions and derived comparison groups. A low/medium/high group is a derived view, not a new independent kind of raw tag.

Catalog descriptions, nutrition and tag confidence values are synthetic fixtures. The original generator's `source=llm` metadata represents the proposed tagging provenance, not an actual live model call. No claim of independently validated nutrition or measured model confidence is intended.

## 4. Information available at a decision

The default demonstration date is 13 July 2026. Actual orders and stock shown for a planning decision must precede that decision's cutoff. Future dates in the synthetic database exist for offline evaluation, not as inputs available to the planner. Weather-dependent forecasts use an issued forecast available at the cutoff and a past-only seasonal fallback for longer horizons.

The policy replay makes an order decision before observing that day's demand. Its capacity measure includes stock immediately after arrivals, before shipping. This avoids giving a planning policy knowledge or space that it would not have at decision time.

## 5. Forecast and detector share a monthly version

LightGBM provides demand forecasts and the expected shares used by detection. Each calendar month uses an immutable version trained only through the preceding month. CUSUM starts again at a model boundary. Human adjustments tied to evidence already absorbed into the new training history retire rather than being silently applied twice. Saved historical plans retain their findings and decisions. Model metadata records training and calibration cutoffs; a production retraining approval service remains outside the local prototype.

A quantile of individual demand is not automatically a quantile of its sum. Aggregate protection-window uncertainty uses an empirical calibration procedure and remains an approximation. The report must show coverage and errors rather than equating an input service-level parameter with achieved fill rate.

CUSUM tracks weather-adjusted attribute share. Block bootstrap calibration, multiple-testing handling and the actual displayed alert gate are separate concepts; report which one each result measures. Shift-share is descriptive attribution of volume, mix and interaction, not proof of causality.

## 6. Explanations require evidence

The investigator compares plausible explanations such as promotion, concentration at one store, weather, a persistent shift or an uncertain signal. Date, district and direction matter. A completed promotion may explain a fading signal. Ground-truth planted events belong in evaluation and must not be used as an answer key by the investigator.

The portable default assistant is **scripted**; the verified local configuration uses **Gemini**. Live conversation selects from validated evidence and planning tools. Both routes use the same mutation logic. Informational questions and scenarios remain read-only, approvals remain human actions, and a remote failure is identified as a fallback. Actual tool results and provider metadata accompany saved messages; progress labels describe observable checks rather than hidden reasoning. An unsupported request must be acknowledged rather than answered with invented analysis.

## 7. Replenishment is a heuristic

Targets cover the wait until the supplier's next order day, lead time and review interval. Existing stock and pipeline reduce need. Orders are rounded to cases and respect minimum quantities; a capacity-constrained SKU may be reduced to zero instead of being forced to retain an infeasible MOQ.

The capacity allocator is a conservative greedy heuristic. It projects known pipeline by arrival date and subtracts issued forecast consumption from existing inventory, clipped at zero per SKU. New orders reserve their space from arrival through the horizon; inherited daily overcapacity does not create headroom on other days. It is not a globally optimal stochastic inventory solver. This conservatism can reduce fill rate; the replay reports the trade-off openly.

## 8. Demo confirmations and clock

Confirming an order creates an auditable synthetic purchase order. It does not send anything to a supplier. Historical stock snapshots were generated by the historical policy and are not retroactively rewritten by user actions. Moving the demo clock changes the as-of view; it is not a full interactive physical-stock simulator.

## 9. Evaluation and release

Use deterministic synthetic seed 42, named baselines and unmodified outcome metrics. Include missed or late detections, null-world false alarms and inventory/service trade-offs. A favourable result must not be manufactured by selecting only successful planted events or changing thresholds after looking at the answer key.

The working branch is `claude/scoop-prototype`. The repository remains private until the owner deliberately approves publication. Do not include sponsor data, private conversation exports, credentials or local model caches in a public release. The competition submission still requires the team's confirmed roster, contribution declaration, team ID and a publicly accessible reviewed release.
