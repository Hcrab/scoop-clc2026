# Scoop

Scoop is a synthetic ice-cream replenishment planner for the Corporate Link Challenge 2026. Its five-step flow connects a weekly demand report to case-level orders, a saved monitoring dashboard, a timed replay and measured results against a moving-average rule. Approvals are local demo records; no supplier order is transmitted.

The **public demo** uses seed 93: one distribution centre, 20 stores, four districts, 75 products, eight suppliers and a 62-pallet cold store. It opens on **27 July 2026** with plan `P20260727`. A quieter **22 June 2026** week is available in Settings. Other seeds are retained for private evaluation and are not selectable in the public interface.

## Quick start

Requirements: Python **3.12+**, PostgreSQL **16 or 17**, Node.js **22+**, pnpm, and an isolated demo database. Run these commands from the repository root. Docker Compose can supply PostgreSQL 16:

```sh
docker compose up -d db
python -m venv .venv
```

Activate the environment and make `backend` importable:

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = 'backend'
```

```sh
# Bash
source .venv/bin/activate
export PYTHONPATH=backend
```

Copy `.env.example` to `.env`. Its database URL matches Compose; change it if using another isolated database. Leave `SCOOP_LLM_PROVIDER=scripted` and the key empty for the portable offline demo. Then install and prepare the public week:

```sh
python -m pip install -r backend/requirements-dev.txt
python -m pip check
python -m scoop.synth.load
python -m scoop.prepare_demo
```

**`scoop.synth.load` replaces the configured database's demo tables.** Run it only for first setup or an intentional full reset. `scoop.prepare_demo` builds the 27 July plan without an LLM call or another data load. Normal app restarts preserve progress. To explicitly prepare a live AI report as well, configure Gemini as described below and run `python -m scoop.prepare_demo --report`; this can consume provider allowance.

After the first-time setup above, build and start the same-origin app with Bash (including Git Bash on Windows):

```sh
bash start.sh
# To use another port:
PORT=8009 bash start.sh
```

The script uses the repository's Python environment, installs frontend dependencies if missing, builds the frontend and runs the server in the foreground. PostgreSQL must be running. Stop with Ctrl+C; the next start preserves the current demo progress. `bash start.sh --help` lists the environment options.

Equivalent manual commands:

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
python -m uvicorn scoop.main:app --app-dir backend --host 127.0.0.1 --port 8008
```

Open [http://127.0.0.1:8008](http://127.0.0.1:8008). FastAPI serves the built frontend and `/api` together; `/health` checks startup and `/docs` lists API routes. First-plan model preparation may take several minutes. For frontend development, `pnpm --dir frontend dev` proxies `/api` to port 8008.

On Windows, `scripts/setup-local.ps1 -LoadData` sets up a separate loopback PostgreSQL database on port 55432, loads the synthetic data **and builds the default plan**. `scripts/start-db.ps1` restarts that database without reloading. `scripts/start-app.ps1` starts the local API and reports its log locations. Pass `-Python` and `-PostgresBin` to setup if the installed paths differ.

## Optional Gemini report and conversation

Set `SCOOP_LLM_PROVIDER=gemini` in the ignored `.env`, provide `GEMINI_API_KEY` in the server process environment, and restart the API. The default model is `gemini-3.8-flash`. A live assistant can investigate synthetic evidence with bounded tools, prepare a saved weekly report, discuss it, and make explicitly requested edits with receipts and Undo. Charts in the report are rendered by the app from saved data; the model does not provide SVG charts. The portable `.env.example` keeps the scripted provider, a US$3 estimated limit and 120 calls. The larger allowance used in the local acceptance run is not the default. See [assistant behavior](docs/ASSISTANT.md).

With an empty key, the app remains usable: the report is a minimal evidence card list, and the scripted assistant supports a limited set of commands. This is not the same autonomous investigation or authored report as live Gemini.

## Demo flow

1. **Report:** read the weekly report and cohort cards, inspect their source data and drilldown, and discuss uncertain changes. Optional context rules can be applied, recomputed and undone. In **This week's direction**, adjust the in-stock target toward **Save space** or **Avoid stockouts** and inspect the live, read-only preview of cases and projected peak before **Apply** commits it; **Reset to auto** selects automatic product targets in the preview for the next **Apply**. The target changes the calculation rather than guaranteeing a measured fulfilment rate.
2. **Orders:** review grouped case quantities, supplier timing, warehouse space and order evidence. Edit quantities or use Undo, export the CSV here, then approve. Approval queues one persisted replay for the effective physical order inputs.
3. **Watch:** inspect warehouse health for the 14 days before the order, then add and arrange server-saved widgets. Each widget plots one measure, grey for recorded values and green for the plan after the order marker. Low cover compares stock with the time until each product's next arrival. Layout and sources continue into Play; editing a widget does not rerun the simulation.
4. **Play:** watch the prepared order replay advance automatically at fixed 2× through a ten-minute clock, about two seconds per simulated day. Warehouse health switches to results since 27 July, with cumulative requests and losses for the current day. From noon, the unfinished day appears as a hollow full-day projection; completed daily points settle at 23:50. The clock shows Day N since the order, and the event feed groups order details. Pause, Resume and Replay are available. The final frame waits for **See results**.
5. **Results:** compare whole-warehouse short units, stockout product-days, lost margin and space use with the moving-average rule under the same physical cold-store capacity. The approved-order outcome and final widget states remain visible; the stock chart places recorded grey, Scoop green and Simple rule orange on one axis.

Settings selects the demo week while preserving each prepared week's progress. Reset restores the selected week's saved initial orders, report and default widgets, clearing edits, context, chat, replay and progression while retaining source data and provider allowance. A first unprepared week needs preparation; repeated same-world resets reuse its initial plan without rebuilding models or calling Gemini. The quiet 22 June week has no cohort cards, although it can have early CUSUM warnings. See the [demonstration guide](docs/DEMO.md) for a presenter sequence.

## Verification and limits

```sh
python -m pytest backend/tests -q
python -m scoop.evaluate
pnpm --dir frontend build
```

API tests need PostgreSQL and use disposable schemas. The ordinary test suite forces the assistant offline and does not spend provider allowance. Model caches live under `data/cache/`; evaluation outputs live under `reports/`. If Windows denies the global pytest temporary directory, use a fresh workspace-local `--basetemp` path that contains no user files.

An earlier P7 revision of this setup recipe was checked from a clean clone with a new database and no copied model cache on Python3.12.14, PostgreSQL17.11, Node24.19.0 and pnpm11.25.0. That revision's empty-key ASGI startup and Edge browser run passed with zero provider calls. This is historical setup evidence, not a fresh-clone result for the current Night 3 application. Commands and output are in [the runtime log](reports/p7-clean-runtime.txt) and [acceptance ledger](docs/overnight-report.md).

The forecast, cohort detector, capacity allocation and Play comparison use synthetic data. The default 27 July report first isolates four strawberry × value-price × water-based products at an estimated +38.1552%. Heat runs 30 July–2 August inside the issued forecast's seven-day skill window; pre-30-July history is unchanged. The ordering target uses a one-sided upper correction, leaving central intervals intact. At the actual 98% target, the same 478 historical calibration windows cover **96.86% before → 98.33% after** (463 → 470 windows); this fitted coverage is not an independent performance estimate.

The [current measured default replay](reports/tuning/demo-walkthrough.json) gives Scoop / Simple rule **4,297 / 6,063 short units**, **36 / 39 stockout product-days**, and **HK$24,271.33 / HK$30,849.11 lost margin**. Results shows both policies and their rounded relative differences: **29% fewer**, **8% fewer** and **21% less**. Both policies share 62 usable pallet positions, peak at 57.9866 pallets and have zero over-capacity days. Initial orders are 2,413 cases with a 61.3046-pallet projected peak. The rule remains 28-day average +25% with unchanged inputs. See [chosen values and reasons](docs/TECHNICAL_DESIGN.md#demonstration-parameters), [full tuning evidence](reports/tuning/final.md), and [earlier measurements](docs/reports/day16-d4.md).

## Guided tour

On first visit, choose **Start the tour** or **Explore on my own**. **Take the tour** in the top bar opens it again. The desktop tour guides ten steps through the same Report, Orders, Watch, Play and Results components, with suggested questions and context/widget choices. Skip or Esc returns to Explore at the default Report. Below 1280 px the welcome offers Explore only.

The tour reads the checked-in `frontend/public/tour-bundle.json`. All tour changes stay in browser memory: no HTTP writes, provider calls or changes to Explore's database. Its five assistant answers were recorded from real Gemini calls and are labelled **Recorded example**. The three context choices contain distinct real orders and complete replays. Normal Play speed remains about two seconds per day, with no pause control in the tour.

To rebuild after changing the default week, prepare its initial template first, then run these commands from the repository root with the backend environment active:

```sh
python scripts/build-tour-bundle.py
# Requires Gemini credentials and provider allowance for the five recordings.
python scripts/record-tour-answers.py
pnpm --dir frontend build
SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test tour.spec.ts
```

The builder copies source data into a private PostgreSQL schema, excludes the evaluation-only ground-truth table, and calls the real API there. It retains that schema for the separate answer-recording command. Rebuild both data and answers before publishing a refreshed tour. A read-only `/api/tour/source` fingerprint rejects stale bundles; missing recordings are not replaced with fabricated answers. Build and recording evidence lives in `reports/night4/`.

The current parameters are optimised for the demonstration scenario. Once real operational data is available, they will be re-optimised on that data.

## Further reading

- [System design](docs/TECHNICAL_DESIGN.md)
- [Product and modelling decisions](DECISIONS.md)
- [Algorithm and evaluation notes](docs/ALGORITHM_NOTES.md)
- [AI, data and dependency disclosure](docs/THIRD_PARTY.md)

The implementation branch is `claude/scoop-prototype`. Publication, main-branch promotion and competition submission remain owner-controlled. The team must confirm its Team ID, roster, contribution declaration and public release before treating these documents as a final submission.
