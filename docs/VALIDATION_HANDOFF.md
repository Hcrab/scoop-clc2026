# Validation handoff — 14 October 2026

This refinement follows the initial `77d745c` delivery. The source conversation remains private. `REQUIREMENTS_AUDIT.md` maps the accepted requirements and the current boundaries.

## Verified local state

- PostgreSQL 17.11 on the isolated local port, with 986,400 synthetic store-product-day demand records, 20 stores, 60 products and eight suppliers.
- Original 6 July and 13 July plans preserved. The 20 July plan completed Discover and Direction approval, including a 96% service preference and Water-based +10% for Kowloon.
- Dragon Fruit Smoothie Cup: original recommendation 25 cases; manually confirmed 26 through the UI. Both values remain visible.
- Fruit / HK Island watch: title and assumption edited during execution without losing scope or rewriting the approved Direction snapshot.
- The 27 July plan is fresh Discover, with six unanswered questions. The previous-week recap reports one confirmed line and 26 cases. Scoped watches carry into the new week.

## Checks

The final central Python run passed **68 tests** in 12.08 seconds. One third-party Starlette/AnyIO deprecation warning remains. The production TypeScript/Vite build passed. Tests use disposable PostgreSQL schemas and force the provider offline.

Meaningful regression coverage includes monthly model cutoffs and monitoring resets, perturbing future data, historical chart provenance, preserved plan decisions, invalid stage/scope rejection, duplicate confirmations, frozen watch approvals, carryover, scoped metrics, concurrent allowance reservation, provider failures and streamed rollback. Six added API cases confirm that English and Chinese negated watch/direction requests do not mutate the offline fallback's plan.

Actual browser testing completed the weekly workflow above and checked narrow, tablet and desktop layouts with requested widths of 390, 768 and 1280. No horizontal overflow was observed. The watch dialog preserves scope, scrolls, traps Tab focus and closes on Escape. Text contrast was checked on the main Discovery view; this is a focused review, not a whole-product accessibility certification.

Real Gemini calls exercised explanation, interpretation, the read-only 35°C scenario, a scoped shortage watch and unscripted Chinese/English questions. The local ledger recorded 25 provider calls and a conservative estimated US$0.384123 at the handoff checkpoint. This is not a billing statement. The default lifetime allowance is 120 calls / estimated US$3, and ordinary tests consume none.

The local delivery includes a PostgreSQL custom-format snapshot. A full restore to a separate empty verification database reproduced all four plans, the demand row count, the 26-case confirmation and the exact Fruit / HK Island watch scope. The verification database was removed; the working database was not replaced.

## Artifacts

The 12-slide editable presentation was rendered and reviewed slide by slide. Package, geometry, Calibri font policy, native table/chart ownership, embedded chart data and artifact-tool re-import checks passed. Native PowerPoint rendering was not executed. Its PDF preview uses the reviewed slide renders. The eight-page technical document was rendered and visually reviewed. Delivery files and a current source archive are provided outside the repository.

## Boundaries

This is a local, single-user synthetic prototype. It does not send supplier orders or simulate a new warehouse inventory history after local confirmation. The capacity allocator is heuristic. Protection-period interval coverage remains 64.49% against a nominal 80%, and several gated signals are late. Gemini prose can still overstate causes, so evidence and planner review remain necessary. No production deployment, public release or competition submission was performed.
