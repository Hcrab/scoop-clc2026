# Scoop

Scoop is a synthetic ice-cream replenishment planner for the Corporate Link Challenge 2026. Its five-step flow connects a weekly demand report to case-level orders, a saved monitoring dashboard, a timed replay and measured results against a moving-average rule. Approvals are local demo records; no supplier order is transmitted.

The **public demo** uses seed 93: one distribution centre, 20 stores, four districts, 75 products, eight suppliers and a 60-pallet cold store. It opens on **27 July 2026** with plan `P20260727`. A quieter **22 June 2026** week is available in Settings. Other seeds are retained for private evaluation and are not selectable in the public interface.

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

Build the frontend and start the same-origin app:

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

1. **Report:** read the weekly report and cohort cards, inspect their source data and drilldown, and discuss uncertain changes. Optional context rules can be applied, recomputed and undone. Adjust the stock-versus-space service preference; it changes the calculation rather than guaranteeing a measured fulfilment rate.
2. **Orders:** review grouped case quantities, supplier timing, warehouse space and order evidence. Edit quantities or use Undo, export the CSV here, then approve. Approval queues one persisted replay for the effective physical order inputs.
3. **Watch:** add and arrange server-saved dashboard widgets. Their layout and sources continue into Play; editing a widget does not rerun the simulation.
4. **Play:** watch the prepared order replay advance automatically at fixed 2× through a ten-minute clock, about two seconds per simulated day. Pause, Resume and Replay are available. The final frame waits for **See results**.
5. **Results:** compare short units, stockout product-days, lost margin and space use with the unchanged moving-average rule. The matched-average-space comparison and the actual approved-order outcome remain visible, alongside final widget states.

Settings changes the demo week and resets planning progress for the current simulation. Reset restores the prepared week's original orders, report and default widgets, clearing manual edits and conversations while retaining source data and provider allowance. New weeks are prepared once; repeated resets reuse their saved initial state. The quiet 22 June week has no cohort cards, although it can have early CUSUM warnings. See the [demonstration guide](docs/DEMO.md) for a presenter sequence.

## Verification and limits

```sh
python -m pytest backend/tests -q
python -m scoop.evaluate
pnpm --dir frontend build
```

API tests need PostgreSQL and use disposable schemas. The ordinary test suite forces the assistant offline and does not spend provider allowance. Model caches live under `data/cache/`; evaluation outputs live under `reports/`. If Windows denies the global pytest temporary directory, use a fresh workspace-local `--basetemp` path that contains no user files.

An earlier P7 revision of this setup recipe was checked from a clean clone with a new database and no copied model cache on Python3.12.14, PostgreSQL17.11, Node24.19.0 and pnpm11.25.0. That revision's empty-key ASGI startup and Edge browser run passed with zero provider calls. This is historical setup evidence, not a fresh-clone result for the current N5 scenario. Commands and output are in [the runtime log](reports/p7-clean-runtime.txt) and [acceptance ledger](docs/overnight-report.md).

The forecast, cohort detector, capacity allocation and Play comparison use synthetic data. In the current designed 27 July example, the first card isolates four strawberry × value-price × water-based products with a +38.1552% estimated change. Its matched comparison uses 36.5785 versus 36.6094 average pallets (0.0844% apart). The plan has **11,160 versus 11,564 short units**, but **89 versus 75 stockout product-days** and **HK$68,203.72 versus HK$61,438.78 lost margin**. The all-three-measures target remains blocked; this is not a policy win or a multi-seed evaluation. See the [work ledger](docs/overnight-report.md) and [demonstration guide](docs/DEMO.md). [Algorithm notes](docs/ALGORITHM_NOTES.md) retain earlier evaluation history. Synthetic results do not establish savings for a real retailer.

## Further reading

- [System design](docs/TECHNICAL_DESIGN.md)
- [Product and modelling decisions](DECISIONS.md)
- [Algorithm and evaluation notes](docs/ALGORITHM_NOTES.md)
- [AI, data and dependency disclosure](docs/THIRD_PARTY.md)

The implementation branch is `claude/scoop-prototype`. Publication, main-branch promotion and competition submission remain owner-controlled. The team must confirm its Team ID, roster, contribution declaration and public release before treating these documents as a final submission.
