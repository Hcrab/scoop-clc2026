# AI-authored weekly reports

Discover has two surfaces: AI report and Trend explorer. The report is assembled after the mechanical scan and additional investigation; the model authors its title, narrative, HTML/CSS and compact charts. Trend explorer independently presents saved programmatic single-attribute and combination results, with actual/expected curves and source details. It remains available without an AI report or live provider.

## Editorial guidance, not a template

Useful reading order: a factual headline; main observations with illustrated evidence and an integrated conclusion; secondary observations with what to watch; aligned Increase / Reduce / Hold recommendations. The model can merge, omit or reorder material according to what this week's evidence supports. Stability requires a relevant comparison; absence of an alarm alone does not establish stability.

One observation has one home: charts carry quantities, prose explains meaning, conclusions connect findings, and actions propose a response. Headline findings replace slogans. Concise, material qualifications belong where they affect a decision; repeated defensive padding does not. These are prompt examples and layout suggestions, not language validators.

Each distinct new observation gets its own illustrated card or report block with its own heading, comparison and explanation. A separate combination finding should not be buried in a regional card's description. Related observations can remain adjacent without losing their identity.

Observation cards use `data-report-card` and `data-report-summary`. The host handles `data-trend-id` buttons by expanding the same card into saved actual/expected daily curves, with prior-year requests when present and time ranges supported by the saved rows. `data-evidence-id` magnifier buttons open query details inline. The model authors HTML/CSS and compact charts; the host supplies the interactive JavaScript. Missing historical observations are not invented.

Charts and prose should explain each other. Use actual-versus-expected lines for timing, common-scale comparisons for districts, contribution bars for composition, and dated inventory/capacity paths for logistics implications. Native expandable sections, chart annotations and evidence links allow detail without repeating a second full dashboard underneath. A specific observation can be a title. Natural summaries and reasonable interpretations are welcome.

No punctuation tests, banned opening words, rigid paragraph counts or automatic sentence rewrites judge the prose. Tool parameters, data scope, evidence references and application permissions still have real operational meaning and remain validated. Graphical facts and units should agree with the returned data.

## Evidence and decisions

Main and secondary observations have no count limits or reserved categories. Clear departures from expectation belong in Main; subtle changes, meaningful stability and tentative leads belong in Secondary. Interpret the departure using the baseline, normal variation, sample and persistence, without a fixed percentage cutoff. A pronounced intersection anomaly belongs in Main even when its affected volume is smaller than a broad category's. Business impact informs explanation and ordering. Reassess the grouping from evidence rather than inheriting a saved narrative's hierarchy; layout follows the content.

The model receives initial findings and programmatic trend candidates, then chooses read-only queries. Saved program trends have T-prefixed source IDs and daily curves; these supplied sources do not consume the additional AI query allowance. Catalog intersections, operational records and purchasing previews reuse the existing forecast, detection, decomposition and ordering modules. Full query results are retained so readers can inspect the origin of a chart or claim. Queries are exploratory; individual follow-up checks are not newly calibrated family-wide discoveries.

The generated page expresses observations, hypotheses and proposed actions. It does not approve strategy or place orders. Discussion remains advisory and the planner controls Continue. Existing saved reports and conversations remain available; explicitly requesting a visual edition of a legacy report can reuse its investigation instead of repeating it. Reading a report never triggers a paid generation.

## Reference practices

The programmatic explorer enumerates cross-dimension single, pair and triple groups with at least three products, deduplicates identical product cohorts, and compares the recent 14-day fractional forecast residual with up to 56 preceding days. It uses a seven-lag Bartlett HAC variance estimate, conservative weekly-block t degrees of freedom, then Benjamini–Yekutieli adjustment across the eligible cohort/district family before ranking. The ranking combines standardized change, volume, persistence and diversity; detailed checks and immediate parent comparisons are retained. This is an approximate exploratory screen alongside the existing calibrated CUSUM monitor, not a claim of calibrated population-wide error control for these synthetic residuals. Relevant method references: [HAC covariance](https://www.statsmodels.org/dev/generated/statsmodels.stats.sandwich_covariance.cov_hac.html) and [dependent-test FDR adjustment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html).

- [Financial Times Visual Vocabulary](https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary): choose a visual according to the relationship being explained.
- [Datawrapper on text in visualizations](https://www.datawrapper.de/blog/text-in-data-visualizations): place explanations close to the relevant graphical evidence.
- [ONS on chart titles](https://digitalblog.ons.gov.uk/2019/01/28/say-what-you-see-the-way-we-write-chart-titles-is-changing/): make the main observation visible in the title when useful.
- [ONS on uncertainty](https://service-manual.ons.gov.uk/data-visualisation/guidance/showing-uncertainty-in-charts): show ranges when they affect interpretation, rather than adding indiscriminate visual noise.
- [IBCS standards](https://www.ibcs.com/standards/page/3/): organize the message and avoid redundant, decorative reporting components.

These are design references, not a claim of certification or a mechanical language policy.

## Prototype observation

The first blind Crosscurrents run used 12 additional queries and explained the broad water/chocolate divergence, but missed both planted normalized-price × format × district interactions. A subsequent user-directed combination query worked; that is assisted exploration, not autonomous discovery. Gemini 4 Argon generated the visual report from saved evidence. The first authoring pass exhausted its output cap; a compact evidence pass succeeded. The displayed sample received human corrections to a goal badge, date/window wording and forecast/capacity labels. These observations do not establish general model reliability.

On 14 October, a live Gemini authoring pass reproduced the revised main/secondary/actions style from saved evidence without human rewriting of its HTML or prose. In-place charts and inline query details were exercised in the browser, including a new query's real prior-year series.

A separate `New season` (seed 92) challenge injects two sustained, district-specific intersections before logistics simulation: lower calorie per 100 ml × premium unit price, and lower sugar per 100 ml × cup. Definitions and negative controls live only in synthetic ground-truth metadata; operational tools cannot access them. The first blind review completed 12 queries but missed both intersections. A second trial added generic contributor → shared attributes → intersection → parent/district guidance, without naming the targets. It queried water-based × premium price, which happens to select the same four products as the first target, and reported their concentration (6,621 requests against 3,857.86 expected, +71.6%). It did not identify the calorie relationship or isolate its exact district scope, and missed the second target. This is partial cohort discovery, not two successful combination discoveries.

The second trial ran in an isolated process and its purchasing preview was unavailable because monthly artifacts were not loaded into that process. Its raw result is retained as an experiment, not installed over the working app report. The first challenge run's operational previews succeeded. Prompt guidance improved the investigation, but autonomous combination coverage remains incomplete.

The `Fresh week` (seed 93) run plants a sustained strawberry × water-based × value-price request increase before the warehouse simulation, with matched 75 ml stick controls. On 14 October the generic scan tested 2,465 cohort/district scopes. The exact four-product intersection ranked fourth in Kowloon: 7,831 requests versus 2,899.81 expected (+170.1%, exploratory adjusted q=0.04057); it also appeared in NT West (+96.8%). The live AI used the supplied program findings and 12 additional operational/group queries. It independently discussed strawberry and local value-tier concentration. Subsequent editorial authoring feedback was needed to isolate the exact three-tag observation as its own card; this is program-assisted discovery with editorial refinement, not a blind model-only discovery claim. The complete source records and daily series remain available to the host while redundant raw checks and program daily rows are omitted from the layout-only prompt.

Browser verification caught three generated chart hooks pointing at broader Q queries despite correct subgroup metrics and evidence links. Those three hooks were corrected to the matching T series; report prose and values were not rewritten. The prompt now explicitly permits T chart sources and requires the source's product and district scope to match the card.
