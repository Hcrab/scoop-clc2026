# Scoop evaluation (synthetic data)

See [algorithm assumptions and limitations](../docs/ALGORITHM_NOTES.md). All numbers come from `python -m scoop.evaluate` on the synthetic world (seed 42). They show the method works on data with known answers; they are not claims about real PARKnSHOP or LOGFLOWS operations.

## 1. Forecast accuracy (monthly rolling origins Apr-Aug 2026)

| Level | Scoop (LightGBM) | Same weekday last week | 28-day moving average |
|---|---|---|---|
| Store x SKU x day (Apr-May), WAPE | 49.5% | 70.7% | 52.5% |
| DC protection period (Apr-Aug), WAPE | 10.9% | - | 10.0% |

Daily p10-p90 interval coverage: 80.0% (target 80%).

## 2. Detection of planted trends

A shared model retrains at each month boundary and CUSUM starts at zero. The table includes seven strong trend/district targets and four weak low-sugar targets. Missing alarms are counted through August 31; alarms over 14 days late are separately reported. Full monthly cutoff, calibration and threshold metadata are in JSON.

CUSUM k = 0.25, initial June threshold h = 3.29 (bootstrap ARL target 90 days; empirical approximation, no exact guarantee). Raw threshold alarms and BH-gated exposures are separately recorded in JSON.

| Event | Group | District | Starts | Raw CUSUM | Days | BH-gated | Days | Weekly check | Days |
|---|---|---|---|---|---|---|---|---|---|
| EV01 | family:fruit | Kowloon | 2026-06-22 | 2026-06-22 | 0 | 2026-07-17 | 25 | 2026-06-28 | 6 |
| EV01 | family:fruit | HK Island | 2026-07-06 | 2026-07-09 | 3 | 2026-07-17 | 11 | 2026-07-12 | 6 |
| EV01 | family:fruit | NT East | 2026-07-20 | 2026-08-12 | 23 | none | - | 2026-07-26 | 6 |
| EV02 | feature:choc_coated | Kowloon | 2026-06-08 | 2026-06-22 | 14 | 2026-06-29 | 21 | 2026-06-21 | 13 |
| EV02 | feature:choc_coated | HK Island | 2026-06-08 | 2026-06-27 | 19 | 2026-07-17 | 39 | 2026-06-28 | 20 |
| EV02 | feature:choc_coated | NT East | 2026-06-08 | 2026-06-25 | 17 | 2026-06-29 | 21 | 2026-06-28 | 20 |
| EV02 | feature:choc_coated | NT West | 2026-06-08 | 2026-06-09 | 1 | 2026-07-17 | 39 | 2026-06-21 | 13 |
| EV03 | health:low_sugar | Kowloon | 2026-06-01 | 2026-06-30 | 29 | 2026-07-25 | 54 | 2026-06-14 | 13 |
| EV03 | health:low_sugar | HK Island | 2026-06-01 | 2026-06-17 | 16 | 2026-07-26 | 55 | 2026-06-21 | 20 |
| EV03 | health:low_sugar | NT East | 2026-06-01 | 2026-06-17 | 16 | 2026-07-31 | 60 | 2026-06-30 | 29 |
| EV03 | health:low_sugar | NT West | 2026-06-01 | 2026-07-14 | 43 | 2026-07-23 | 52 | 2026-06-30 | 29 |

Missed trend/district pairs: raw 0/11; BH-gated 1/11.
Held-out protection interval coverage: 64.5% across 780 rolling-origin windows. Each version uses calibration outcomes strictly before its own test month.

Mean delay: CUSUM 16.5 days vs weekly check 15.9 days.

False alarms in a twin world with no planted events: 547 alarm episodes over 248 charts x 92 days = 2.158 per chart per 90 days; actual BH-gated false-alarm episodes: 0.

Weak signal (low-sugar drift, +12% over three months): pooled network review alarms on 2026-06-02; first single-district alarm 2026-06-17.

## 3. Investigator labels

8 of 12 findings that match a planted event got the right label (67%).

| Week | Finding | Districts | Label | Planted event | Expected |
|---|---|---|---|---|---|
| 2026-06-29 | Water-based | Kowloon | persistent | EV01 | persistent |
| 2026-06-29 | Creamy | NT East | one_off | - | noise |
| 2026-06-29 | Chocolate family | Kowloon | one_off | EV02 | persistent |
| 2026-06-29 | Crunchy | Kowloon | one_off | EV02 | persistent |
| 2026-07-20 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-20 | Water-based | HK Island, Kowloon, NT East | persistent | EV01 | persistent |
| 2026-07-20 | Higher sugar | Kowloon, NT West | persistent | EV02 | persistent |
| 2026-07-20 | Chocolate family | HK Island, NT East, NT West | one_off | EV02 | persistent |
| 2026-07-20 | Cones | HK Island, NT West | one_off | EV04 | one_off |
| 2026-07-20 | Classic family | Kowloon | one_off | - | noise |
| 2026-07-27 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-27 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-07-27 | Crunchy | HK Island, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-27 | Classic family | Kowloon | mirror | - | noise |
| 2026-07-27 | Mixed | HK Island, Kowloon | mirror | - | noise |
| 2026-07-27 | Mid price | HK Island, Kowloon | mirror | EV02 | persistent |

## 4. Policy replay, Jun-Aug 2026

| Policy | Fill rate | Lost units | Lost margin (HKD) | Avg closing pallets | Max closing pallets | Days over closing capacity | Peak before shipping | Days over before shipping | POs |
|---|---|---|---|---|---|---|---|---|---|
| fixed reorder point x1.25 | 79.06% | 139,708 | 926,623 | 16.0 | 36.3 | 0 | 40.1 | 0 | 797 |
| history x1.00 | 92.04% | 53,105 | 358,905 | 19.5 | 32.6 | 0 | 38.2 | 0 | 798 |
| history x1.15 | 97.30% | 18,010 | 119,269 | 26.3 | 43.5 | 0 | 49.3 | 0 | 798 |
| history x1.25 | 98.72% | 8,519 | 55,400 | 32.0 | 51.0 | 0 | 57.4 | 0 | 798 |
| history x1.40 | 99.73% | 1,788 | 11,529 | 41.2 | 63.1 | 2 | 69.4 | 13 | 798 |
| scoop_forecast @ CR | 96.73% | 21,837 | 133,698 | 24.8 | 42.6 | 0 | 48.6 | 0 | 798 |
| scoop_forecast @ 92% | 97.82% | 14,513 | 87,956 | 27.8 | 48.8 | 0 | 54.9 | 0 | 798 |
| scoop_full @ CR | 97.07% | 19,520 | 121,782 | 24.5 | 42.3 | 0 | 48.5 | 0 | 798 |
| scoop_full @ 85% | 97.78% | 14,840 | 92,657 | 26.3 | 46.4 | 0 | 52.6 | 0 | 798 |
| scoop_full @ 92% | 98.20% | 12,004 | 74,645 | 27.5 | 48.6 | 0 | 54.9 | 0 | 798 |
| scoop_full @ 96% | 98.58% | 9,449 | 58,812 | 29.0 | 52.0 | 0 | 58.2 | 0 | 798 |

fixed reorder point = a frozen May 4-31 mean setting the reorder point and fixed seven-day order quantity; checked only on supplier weekdays. It never adapts to later demand. Historical baselines are unconstrained. history xB = 28-day moving average x (lead + 7 days) x buffer B (the policy that produced the synthetic history uses 1.25). scoop_forecast = order-up-to on the LightGBM protection-period forecast. scoop_full = scoop_forecast plus the weekly CUSUM findings with the AI draft directions accepted. Directions and CUSUM reset on a model update. @ CR = newsvendor critical ratio per SKU; @ 92% = fixed service level. Compare policies at similar average pallets: the question is how much stock buys how much fill rate.


Unmatched significant findings: 4; total significant findings: 16. Matched true-trend findings labeled persistent: 7/11; matched temporary findings kept neutral: 1/1.
Weak candidates later confirmed by BH within 14 days: 18/36 complete followups; 8 late-period candidates are censored. Random exploratory comparator: 21/120 (different scopes; no formal superiority claim).

## Monthly forecast evidence

| Version | Trained through | Calibration outcomes through | Daily WAPE | Daily coverage | Pinball p10 / p90 | Protection WAPE | Protection coverage |
|---|---|---|---|---|---|---|---|
| M202604-v1-s42 | 2026-03-31 | 2026-03-31 | 50.06% | 79.54% | 0.348 / 0.529 | 4.04% | 85.00% |
| M202605-v1-s42 | 2026-04-30 | 2026-04-30 | 48.98% | 80.54% | 0.384 / 0.579 | 5.69% | 57.78% |
| M202606-v1-s42 | 2026-05-31 | 2026-05-31 | 46.76% | 80.24% | 0.435 / 0.655 | 5.02% | 87.50% |
| M202607-v1-s42 | 2026-06-30 | 2026-06-30 | 45.87% | 79.05% | 0.517 / 0.816 | 14.04% | 40.56% |
| M202608-v1-s42 | 2026-07-31 | 2026-07-31 | 46.33% | 78.79% | 0.524 / 0.836 | 17.08% | 66.11% |

BH-gated missed strong targets: 1/7; missed weak targets: 0/4. Late gated detections (>14 days): 9.
Bounded weekly weak-review audit: 130 checks across 14 dates; maximum ten checks per date. Exploratory results never automatically change purchases.
