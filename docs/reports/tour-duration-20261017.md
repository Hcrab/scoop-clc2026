# Guided-tour duration rehearsal — 17 October 2026

Three complete Playwright runs followed the native 14-step prompts at 1440×900. Reading dwell is explicitly modelled at **200 English words/minute** (minimum two seconds), with extra time to inspect charts, the expanded trend derivation, the order ledger and Results. This is a paced walkthrough estimate, not a study with human participants. Wall times include loading, welcome/end, clicks and actual playback; errors and HTTP writes are zero. Reading the Play instructions overlaps playback, so playback time is not added twice.

| Branch | Question | Added widgets | Playback speed | Whole experience | Actual replay |
|---|---|---|---|---|---|
| summer | why | stock + space | 2× | 5:21 | 32.0 s |
| growing | heat | space + cover | 4× | 5:03 | 16.2 s |
| unchanged | skip | stock | 8× | 4:29 | 8.2 s |

Raw per-step timestamps, word counts, modelled reading/inspection time and actual completion events: `reports/tour3/duration-{summer,growing,unchanged}.json`. Reproduce with `SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour-duration.spec.ts`.
