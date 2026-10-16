# Default demo: before tuning diagnosis

Frozen run: 27 July–11 August 2026, 16 days, margin objective, automatic service level, 66 pallets. Scoop loses HKD 7,276.58 more margin and 284 more units than the 28-day-average ×1.25 rule. The main actionable evidence is insufficient initial protection stock followed by catch-up orders arriving after shortages. No new candidate was run.

| Measure | Scoop | Rule | Scoop minus rule |
|---|---:|---:|---:|
| Fill rate | 96.781% | 96.925% | -0.144 pp |
| Lost units | 6,347.00 | 6,063.00 | 284.00 |
| Lost margin HKD | 38,125.69 | 30,849.11 | 7,276.58 |
| Average closing pallets | 37.97 | 37.76 | 0.22 |
| Peak pre-shipment pallets | 57.99 | 57.99 | 0.00 |
| Stockout product-days | 52.00 | 39.00 | 13.00 |
| Ending units | 70,564.00 | 52,004.00 | 18,560.00 |
| Ordered cases | 8,352.00 | 7,917.00 | 435.00 |

## Protection stock and lead-time traces

The five largest positive margin-loss differences total HKD 9,196.21; benefits elsewhere offset part of this gross loss. Rows are selected by observed excess loss, so their forecast bias is not a catalog-wide estimate. All had zero initial capacity cuts. Targets and case counts match frozen `d4-orders.json` for all 75 products.

| Product | Protection dates | p50 / target / actual units | CR | Opening stock + inherited pipeline | First cases Scoop / rule | Arrival | Excess margin HKD |
|---|---|---:|---:|---:|---:|---|---:|
| IC010 Mango Sticky Rice Bar | 07-27–08-10 (15d) | 6382.9 / 6940.1 / 8046 | 0.9632 | 1058 + 3800 | 53 / 71 | 08-04 | 3,420.00 |
| IC014 Green Apple Sorbet Tub | 07-27–08-11 (16d) | 697.2 / 770.9 / 848 | 0.9685 | 182 + 492 | 17 / 32 | 08-05 | 1,501.92 |
| IC064 Strawberry Puree Sorbet Bar | 07-27–08-11 (16d) | 5639.5 / 6148.8 / 6450 | 0.9618 | 1610 + 2840 | 43 / 48 | 08-05 | 1,468.00 |
| IC040 Mango Mochi 6-Pack | 07-27–08-10 (15d) | 881.6 / 973.3 / 1101 | 0.9721 | 221 + 468 | 24 / 31 | 08-04 | 1,408.68 |
| IC075 Strawberry Reserve Cream Bar | 07-27–08-11 (16d) | 2599.1 / 2874.1 / 3038 | 0.9664 | 1079 + 1120 | 17 / 24 | 08-05 | 1,397.61 |

First orders cover lead + review + wait until supplier order day: 15 days for Tuesday/7-day-lead products, 16 for Monday/9-day-lead products. New replenishment arrives at the next cycle boundary, so Monday reruns cannot retrospectively fill the earlier target gap.

- **IC010:** 53 cases placed 28 Jul, 2,120 units arrive 4 Aug; the rule ordered 71 cases (720 more units). Closing stock falls to 96 on 8 Aug, then loses 648 and 420 units on 9–10 Aug. The 167-case automatic order placed 4 Aug arrives 11 Aug (6,680 units), after the loss; ending stock is 6,234. Rule loss 348 units versus Scoop 1,068.
- **IC014:** 17 cases placed 27 Jul arrive 5 Aug (102 units), versus rule 32 cases/192 units. Closing stock is 7 on 9 Aug; loses 41 and 31 units on 10–11 Aug. The 105-case automatic order placed 3 Aug arrives 12 Aug, beyond replay. Rule loses 0.
- **IC064:** 43 cases placed 27 Jul arrive 5 Aug (1,720 units), versus 48/1,920. Closing stock 69 on 10 Aug then loses 280 on 11 Aug. The 110-case automatic order placed 3 Aug arrives 12 Aug; rule loses 80, exactly 200 fewer units, matching its larger first delivery.
- **IC040:** 24 cases placed 28 Jul arrive 4 Aug (288 units), versus 31/372. Closing stock 16 on 8 Aug then loses 60 and 64 on 9–10 Aug. The 100-case automatic order placed 4 Aug arrives 11 Aug (1,200 units), ending at 1,148; rule loses 40, exactly 84 fewer units.
- **IC075:** 17 cases placed 27 Jul arrive 5 Aug (680 units), versus 24/960. Closing stock 114 on 9 Aug then loses 35 and 124 on 10–11 Aug. The 60-case automatic order placed 3 Aug arrives 12 Aug; rule loses 0.

Daily demand, receipts, closing inventory, loss, orders and pending pipeline for both policies are embedded in the companion JSON. The first protection actual/p50 ratios are 1.261,1.216,1.144,1.249,1.169 respectively. These establish local underprediction; they do not prove that all forecast means need an uplift.

## What the evidence supports

- **Holding cost: actionable hypothesis.** The 2.5% cost per cycle includes 1% storage/financing plus 1.5% summer carryover/markdown. Its implied CRs are 0.9610–0.9735. A cheaper business estimate of excess stock would raise protection targets before long supplier lead times lock in shortage. The replay scores lost margin, not holding/markdown expense, so a higher-stock policy can improve that display without proving better net economics.
- **CR ceiling: inactive initial constraint.** No initial CR reaches 0.98. Raising only the ceiling changes no initial order under the current holding rate.
- **Calibration tail: small and pooled.** The saved 478 past-only mature windows score 97.071% covered versus mean requested 96.770%; at 0.968 the correction is 0.021626 times forecast. This is calibration-set coverage, not a held-out guarantee. By origin, corrected coverage is 100% for June 1/8/15/22,96.0% June 29,86.67% July 6 and 96.43% July 13 (only 28 mature products). Pooling older quiet weeks can conceal recent upper-tail misses.
- **Forecast bias and timing: observed locally, global cause unproved.** The selected protection actuals exceed even calibrated targets by 77–1,106 units. Later order volumes rise, but arrive too late for the specific first-cycle shortages. These are normal mean lead times, not observed supplier delays. First-week stock is frozen from Monday, later automatic decisions use post-shipment stock; the rule reconstructs pre-shipment stock (`on_hand + ship`) when calculating its order. That convention can help explain larger later Scoop orders and ending stock, and should be kept consistent when interpreting interventions.
- **Capacity approximation: not the binding initial cause.** All 75 initial lines have zero cuts. The initial projected peak is 61.3046 pallets, identical to the inherited-only projected peak; physical maximum is 57.9866, leaving 8.0134 pallets. Both policies have zero over-capacity days and zero deferred receipt units. Source projection consumes issued forecasts and uses expected inherited arrival dates; physical replay uses realized demand and received dates where present. These differences make projection and physical maxima distinct. Dated projection is a heuristic; no evidence here attributes these losses to capacity allocation.

## Global values worth measuring

Each is a separate hypothesis, not a candidate result. Keep supplier dates, opening inventory and policy inputs fixed while measuring the complete physical replay, including later automatic orders and end stock.

- **holding_rate: 0.025 → 0.01.** Treat one-cycle excess as storage/financing only when summer stock can still sell, removing the additional 1.5% markdown provision. Raises margin-derived critical ratios to the existing .98 cap; may increase first orders before irreversible lead-time gaps. unmeasured; compare losses, stock and capacity, including the later automatic orders.
- **global_forecast_mean_multiplier: 1.0 → 1.05.** A modest common allowance for recent demand growth is consistent with the fully observed July 6 calibration origin averaging actual/forecast 1.061. Apply to forecast mean consistently in targets and capacity consumption, rather than inserting SKU-specific cases; only if parent chooses a calibrated global bias experiment. hypothesis; pooled recent bias is not proof of a persistent global error.
- **upper_calibration_lookback_days: 56 → 28.** Give the last month of trading more weight when earlier quiet weeks dominate a summer demand calibration. Same past-only finite-rank correction, newer origins; assess mature-window counts and supplier/lead-time skew. unmeasured; July 13 has only 28 mature SKUs, so shorter lookback can overrepresent shorter leads.

A fixed 0.98 service target largely duplicates the critical-ratio change from holding 0.01 with the current cap; it need not consume a separate initial experiment. Raising capacity or the CR ceiling alone is not supported as a first intervention.

## Evidence and separation

`reports/d4-results.json`, `d4-replay.json.gz`, `d4-orders.json`, `d4-upper-calibration.json`, `d4-upper-calibration-windows.csv`, and `d4-walkthrough.json`; hashes and exact read-only database rows are captured in the JSON. Baseline catalog, supplier, purchase-suggestion and plan-summary SELECTs were read from public PostgreSQL; every first target and order quantity was checked against the frozen d4 file.

Inspected operational source: `algorithms/replenish.py` (holding rate/CR/capacity removal), `algorithms/protection_calibration.py` (56-day past-only upper correction), `algorithms/forecast.py` (protection wait and windows), `planning.py` (cohort-adjusted mean/demand projection), `play.py` (supplier dates/autopilot/rule stock convention), `intraday.py` (timing presentation). No answer-key reads/imports found in inspected operational paths. Only identifier-level search was used to audit generator/challenge separation; answer-key contents were not opened or used. This is a static scoped audit.

Only the two assigned reports were written. No source/runtime/Goal changes, simulations, provider calls, API mutations, commit or push were performed.
