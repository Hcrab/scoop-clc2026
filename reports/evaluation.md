# Scoop evaluation (synthetic data)

See [algorithm assumptions and limitations](../docs/ALGORITHM_NOTES.md). All numbers come from `python -m scoop.evaluate` on the synthetic world (seed 42). They show the method works on data with known answers; they are not claims about real PARKnSHOP or LOGFLOWS operations.

## 1. Forecast accuracy (holdout Apr-May 2026)

| Level | Scoop (LightGBM) | Same weekday last week | 28-day moving average |
|---|---|---|---|
| Store x SKU x day, WAPE | 49.5% | 70.7% | 52.5% |
| DC protection period, WAPE | 3.4% | - | 10.5% |

Daily p10-p90 interval coverage: 80.0% (target 80%).

## 2. Detection of planted trends

CUSUM k = 0.25, threshold h = 3.81 (bootstrap ARL target 90 days; empirical approximation, no exact guarantee). Raw threshold alarms and BH-gated exposures are separately recorded in JSON.

| Event | Group | District | Starts | Raw CUSUM | Days | BH-gated | Days | Weekly check | Days |
|---|---|---|---|---|---|---|---|---|---|
| EV01 | family:fruit | Kowloon | 2026-06-22 | 2026-06-22 | 0 | 2026-06-30 | 8 | 2026-06-28 | 6 |
| EV01 | family:fruit | HK Island | 2026-07-06 | 2026-07-09 | 3 | none | - | 2026-07-12 | 6 |
| EV01 | family:fruit | NT East | 2026-07-20 | none | - | none | - | 2026-07-26 | 6 |
| EV02 | feature:choc_coated | Kowloon | 2026-06-08 | 2026-06-22 | 14 | 2026-06-30 | 22 | 2026-06-21 | 13 |
| EV02 | feature:choc_coated | HK Island | 2026-06-08 | 2026-06-27 | 19 | 2026-07-11 | 33 | 2026-06-28 | 20 |
| EV02 | feature:choc_coated | NT East | 2026-06-08 | 2026-06-25 | 17 | 2026-06-30 | 22 | 2026-06-28 | 20 |
| EV02 | feature:choc_coated | NT West | 2026-06-08 | 2026-06-15 | 7 | 2026-06-30 | 22 | 2026-06-21 | 13 |

Missed trend/district pairs: raw 1/7; BH-gated 2/7.
Held-out protection interval coverage: 83.3% across 120 windows. Calibration and validation outcomes do not overlap.

Mean delay: CUSUM 10.0 days vs weekly check 13.0 days.

False alarms in a twin world with no planted events: 368 alarm episodes over 248 charts x 92 days = 1.452 per chart per 90 days; actual BH-gated false-alarm episodes: 0.

Weak signal (low-sugar drift, +12% over three months): pooled network review alarms on 2026-06-02; first single-district alarm 2026-06-14.

## 3. Investigator labels

19 of 25 findings that match a planted event got the right label (76%).

| Week | Finding | Districts | Label | Planted event | Expected |
|---|---|---|---|---|---|
| 2026-07-06 | Chocolate flavour | Kowloon | one_off | EV02 | persistent |
| 2026-07-06 | Water-based | Kowloon | persistent | EV01 | persistent |
| 2026-07-06 | Cones | HK Island, Kowloon, NT East, NT West | one_off | EV04 | one_off |
| 2026-07-06 | Chocolate-coated | NT East, NT West | one_off | EV02 | persistent |
| 2026-07-06 | Higher sugar | Kowloon | one_off | EV02 | persistent |
| 2026-07-06 | Value price | NT East | persistent | EV03 | persistent |
| 2026-07-13 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-07-13 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-13 | Mid price | Kowloon | one_off | EV02 | persistent |
| 2026-07-13 | Cones | HK Island, Kowloon, NT East, NT West | one_off | EV04 | one_off |
| 2026-07-20 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-07-20 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-20 | Crunchy | HK Island, Kowloon, NT East, NT West | one_off | EV02 | persistent |
| 2026-07-20 | Mid price | HK Island, Kowloon, NT East | one_off | EV02 | persistent |
| 2026-07-20 | Chocolate flavour | NT East | persistent | EV02 | persistent |
| 2026-07-20 | Mixed | HK Island, Kowloon, NT East, NT West | one_off | - | noise |
| 2026-07-27 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-07-27 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-27 | Crunchy | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-07-27 | Low-sugar claim | HK Island, Kowloon, NT East, NT West | persistent | EV03 | persistent |
| 2026-08-03 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-08-03 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-08-03 | Crunchy | Kowloon, NT East | persistent | EV02 | persistent |
| 2026-08-03 | Mixed | HK Island, Kowloon, NT East, NT West | one_off | - | noise |
| 2026-08-03 | Creamy | HK Island, NT East, NT West | persistent | - | noise |
| 2026-08-10 | Water-based | HK Island, Kowloon, NT East, NT West | persistent | EV01 | persistent |
| 2026-08-10 | Chocolate-coated | HK Island, Kowloon, NT East, NT West | persistent | EV02 | persistent |
| 2026-08-10 | Mixed | Kowloon, NT East, NT West | persistent | - | noise |
| 2026-08-10 | Creamy | HK Island | persistent | - | noise |
| 2026-08-10 | Low-sugar claim | HK Island, Kowloon, NT East, NT West | persistent | EV03 | persistent |

## 4. Policy replay, Jun-Aug 2026

| Policy | Fill rate | Lost units | Lost margin (HKD) | Avg closing pallets | Max closing pallets | Days over closing capacity | Peak before shipping | Days over before shipping | POs |
|---|---|---|---|---|---|---|---|---|---|
| history x1.00 | 92.04% | 53,105 | 358,905 | 19.5 | 32.6 | 0 | 38.2 | 0 | 798 |
| history x1.15 | 97.30% | 18,010 | 119,269 | 26.3 | 43.5 | 0 | 49.3 | 0 | 798 |
| history x1.25 | 98.72% | 8,519 | 55,400 | 32.0 | 51.0 | 0 | 57.4 | 0 | 798 |
| history x1.40 | 99.73% | 1,788 | 11,529 | 41.2 | 63.1 | 2 | 69.4 | 13 | 798 |
| scoop_forecast @ CR | 92.80% | 48,011 | 310,612 | 19.6 | 32.5 | 0 | 36.8 | 0 | 798 |
| scoop_forecast @ 92% | 94.77% | 34,909 | 219,469 | 21.5 | 32.5 | 0 | 37.2 | 0 | 798 |
| scoop_full @ CR | 93.77% | 41,546 | 281,491 | 19.1 | 32.5 | 0 | 36.8 | 0 | 798 |
| scoop_full @ 85% | 95.04% | 33,090 | 222,755 | 20.2 | 32.5 | 0 | 36.8 | 0 | 798 |
| scoop_full @ 92% | 95.80% | 28,011 | 186,648 | 20.9 | 32.5 | 0 | 36.8 | 0 | 798 |
| scoop_full @ 96% | 96.54% | 23,078 | 151,481 | 21.9 | 32.5 | 0 | 36.8 | 0 | 798 |

history xB = 28-day moving average x (lead + 7 days) x buffer B (the policy that produced the synthetic history uses 1.25). scoop_forecast = order-up-to on the LightGBM protection-period forecast. scoop_full = scoop_forecast plus the weekly CUSUM findings with the AI draft directions accepted. @ CR = newsvendor critical ratio per SKU; @ 92% = fixed service level. Compare policies at similar average pallets: the question is how much stock buys how much fill rate.
