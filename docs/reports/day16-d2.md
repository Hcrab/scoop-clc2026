# Day 16 — D2 evidence

D1 was accepted and pushed as `03fa6c9` before D2 began. D2 changes presentation and supplies recorded warehouse totals to the existing dashboard response; it does not change forecasts, orders, capacity, scenario or policy settings.

## Acceptance

- ✅ Report heading: `Merchandising & planning checks`, sentence case, normal heading colour `rgb(27, 56, 43)`, no text transformation. `docs/screenshots/d2-report-checks.png` was personally inspected. The saved D1 report had two structured, AI-authored questions but no planning-check section in its HTML; those same questions are now visible under this heading. `reports/d2-report-heading.json` records unchanged claims, queries and widget specifications, refreshed reset template and zero new provider calls. Future report guidance requests this presentation without policing natural-language output.
- ✅ Results: `docs/screenshots/d2-results.png` was personally inspected. Warehouse closing stock uses a single SVG and axis: recorded history grey, Scoop green and Simple rule orange. The 28-day history ends on 26 July at 63,335 units; both simulations share that anchor. Missing history remains a gap. Detailed stock, fill and capacity widgets also compare policies in Results; Watch and Play continue showing Scoop only. Demand retains blue recorded and lighter blue simulated segments. The three headline outcomes and See full comparison remain.

## Verification

| Check | Evidence | Result |
|---|---|---|
| Backend history cutoff, missing data and dashboard behaviour | `reports/d2-history-tests.txt` | 12 passed |
| Frontend shared axis, common anchor, null gaps, Results-only comparison, demand palette and existing D1 behaviour | `reports/d2-frontend-python.txt` | 18 passed |
| TypeScript and production build | `reports/d2-build.txt` | Pass |
| Actual API, browser report → Orders → Watch → Play → Results, no response mocks | `frontend/e2e/day16-d2.spec.ts`, `reports/d2-browser.txt/json` | 1 passed, 1.5 min; no page errors |

The browser verifies the report heading's computed style and three actual SVG policy strokes, opens See full comparison, and resets to the exact initial orders afterward. It makes no paid AI calls.

## Unchanged outcomes before D3

| Outcome, 27 July–11 August | Scoop plan | Simple rule |
|---|---:|---:|
| Units short | 11,160 | 11,564 |
| Stockout product-days | 89 | 75 |
| Lost margin, HK$ | 68,203.72 | 61,438.78 |
| Physical peak pallets | 57.9866 | 57.9866 |

These are the same replay results as D1. D3 has not yet begun; its only authorised changes are protection-period split-conformal calibration and illustrative heat timing.
