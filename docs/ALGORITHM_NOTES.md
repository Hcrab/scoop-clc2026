# How the planning engine works

Each week the engine runs four steps: forecast normal demand, look for early signals, find which products are really changing, and calculate the order. The planner's context can adjust the result before the order is final. The algorithms never read the planted answers in the synthetic data.

## 1. Forecast (LightGBM)

LightGBM predicts daily requests per store and product from the calendar, recent demand, promotions and the weather forecast issued the day before, so no future weather is used. Interactions such as temperature × format let it learn that water ices react to heat more than creamy tubs. Models are retrained monthly and frozen within the month.

For ordering, the forecast is summed over each product's protection period: lead time plus the time to the next order. Split-conformal calibration on recent errors sets the upper range, so a 98% target covers about 98% of past periods.

## 2. Early warnings (CUSUM)

For each attribute, such as a flavour or a format, a CUSUM monitor adds up the daily gaps between actual and forecast demand and warns when the total crosses a bootstrap threshold. Benjamini–Hochberg control keeps false alarms low across many attributes.

## 3. Trend finder (tree + empirical Bayes)

Real changes usually sit in a combination of attributes. For each product and district, Scoop compares actual against forecast demand over the last 14 days and the 56 days before. Because the forecast already includes the weather, weather drops out of this measure.

A conditional inference tree groups products by attributes and district, and a block permutation test keeps only splits unlikely by chance. Two-level empirical Bayes then gives each product a stable demand factor, pulling noisy estimates toward their group.

The planner can add what the data cannot know: mark a trend as a one-off, give it an end date, cap it, or set their own expected change. Each choice is applied to the trend group as a prior.

## 4. Order (order-up-to + newsvendor)

Scoop orders up to a target stock level, minus stock on hand and on the way, in whole cases and supplier minimums. The service level comes from the newsvendor ratio of margin against margin plus holding cost, bounded between 50% and 98%. If the cold store would overflow on any delivery day, cases are cut first where they earn the least margin per pallet. Every line keeps its calculation.

## Limits

- The trend finder only sees changes that attributes or districts can describe, with at least three products per group.
- Monthly retraining may delay a trend that starts mid-month.
- The demo settings were tuned for the synthetic world and will be re-tuned on real data.

## Code

| Step | Where in `backend/scoop/` |
| --- | --- |
| Forecast | `algorithms/forecast.py`, `algorithms/protection_calibration.py` |
| Early warnings | `algorithms/cusum.py` |
| Trend finder and context | `algorithms/cohort_model.py`, `algorithms/cohort_overrides.py` |
| Order | `algorithms/replenish.py`, `order_ledger.py` |
| Evaluation | `evaluate.py` (`python -m scoop.evaluate`) |
