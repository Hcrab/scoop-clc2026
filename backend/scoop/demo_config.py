"""One public demo; other seeds remain available to offline evaluation."""

DEMO_SEED = 93
DEMO_WEEK = "2026-07-27"
QUIET_WEEK = "2026-06-22"
DEMO_SCENARIO = "fresh-week"
# Authorized illustrative-demo exception after the corrected .05 tree stopped
# at root p=0.0502512563. Other worlds and pure statistical fixtures retain .05.
DEMO_COHORT_ALPHA = .10
# Night 3 start-state correction: default projected peak ~61.3 / 66 = 92.9%.
# This changes physical demo capacity, leaving both policies' settings unchanged.
DEMO_CAPACITY_PALLETS = 66
