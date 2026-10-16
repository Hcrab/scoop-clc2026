# Scoop: Results and guided tour — 17 October 2026

R0 is accepted. Tour work starts after the R0 push. The previous full report is archived at [pre-tour-20261016.md](reports/pre-tour-20261016.md). Requirements and final copy: [night4-protocol.md](reports/night4-protocol.md).

## One-page status

| Phase | Status | Evidence |
|---|---|---|
| R0 Results | ✅ Accepted | 18 focused checks, build, real 1440×900 screenshot |
| T1 Tour entry and coach | ❌ Not started | R0 first |
| T2 Isolated fixture bundle | ❌ Not started | R0 first |
| T3 Context branches | ❌ Not started | R0 first |
| T4 Recorded Gemini answers | ❌ Not started | Recording only; existing night-3 allowance |
| T5–T6 Verbatim tour and controls | ❌ Not started | R0 first |
| T7 Three-run browser acceptance/docs | ❌ Not started | R0 first |

The local LOGFLOWS PDF stays local and is excluded from this phase’s published history. App copy from the handoff is final. No tuning is authorised by this handoff.

## R0 — accepted

- ✅ Three real comparison cards: Units short **Simple rule 6,063 / Scoop 4,297 / 29% fewer**; Stockout product-days **39 / 36 / 8% fewer**; Lost margin **HK$30,849 / HK$24,271 / 21% less**. Evidence: [stored replay and rendered values](../../reports/night4/r0-results.json), [1440×900 screenshot](screenshots/r0-results.png), personally reviewed.
- ✅ The muted footer matches the handoff verbatim. `rg -n -i avoided reports/night4/r0-results-ui.txt` → exit **1**, no matches. Removed the Results Illustrative scenario line and old duplicate footer paragraphs.
- ✅ `node --test frontend/tests/results-metrics.test.cjs frontend/tests/results-comparison.test.cjs frontend/tests/report-product-icons.test.cjs` → **18 passed**; `pnpm --dir frontend build` passed. Equal and worse badges use coral `more`; a positive Scoop loss against a zero rule has no fabricated finite percentage. The default replay has no zero denominator.
- ✅ No algorithms, thresholds, costs, buffers, stored orders or replay values changed. Local PDF and its rebuild assets remain excluded from published history; the original local commit is retained on `local/logflows-overview-20261016`. Gemini before recording: **177 calls / $18.326137** against the night-3 cumulative cap **$26.897085** (remaining **$8.570948**).
