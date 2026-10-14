# Scoop

Trend-aware ice-cream replenishment planning for the Corporate Link Challenge 2026.

Scoop helps a cold-store planner review demand changes, decide what to buy more or less of, and turn those decisions into case quantities under supplier and warehouse constraints. The weekly flow is **Discover -> Direction -> Execute & watch**, with a plan discussion that follows the selected finding and stage.

The local prototype uses synthetic data: one DC, 20 stores, four districts, 60 SKUs and eight suppliers. Its initial clock is **13 July 2026**; the demo controls can advance it through August. The portable default works offline. Optional Gemini assistance uses real tool calls and an explicit offline fallback. Purchase confirmations are local records; no real supplier orders are sent.

## Quick start

Requirements: Python 3.12, PostgreSQL 16 or 17, Node.js 22+ and pnpm. Commands below run from the repository root. The verified Windows setup uses PostgreSQL 17.11; Compose provides PostgreSQL 16 for a portable database option.

### Database and Python

Start the bundled Compose database, or provide an existing empty PostgreSQL database:

```sh
docker compose up -d db
python -m venv .venv
```

Activate the environment:

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

Install dependencies and copy `.env.example` to `.env`. Set `DATABASE_URL` to the intended **isolated demo database**. The default matches Compose.

```sh
python -m pip install -r backend/requirements-dev.txt
python -m pip check
python -m scoop.synth.load
```

**The load command replaces all tables in the configured database. Run it only for first setup or an intentional demo reset.** Normal restarts preserve existing data and decisions.

On the original Windows machine, `scripts/setup-local.ps1 -LoadData` creates the virtual environment and starts a separate loopback database on port 55432. Pass `-Python` and `-PostgresBin` to use other installed locations. `scripts/start-db.ps1` restarts that isolated database without loading data again.

### Frontend and application

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
python -m uvicorn scoop.main:app --app-dir backend --host 127.0.0.1 --port 8008
```

Open **http://127.0.0.1:8008**. FastAPI serves the built frontend and `/api` from the same origin. API documentation is at `/docs`; `/health` confirms basic startup. The first weekly plan may take longer while local models and monitoring artifacts are computed. Subsequent plans reuse the cache.

For frontend development, run `pnpm --dir frontend dev` alongside the API. Vite proxies `/api` to port 8008. The PowerShell helper `scripts/start-app.ps1` starts a hidden local API process with log files; inspect its output for process and log locations.

### Tests and evaluation

```sh
python -m pytest backend/tests -q
python -m scoop.evaluate
pnpm --dir frontend build
```

API tests require a running configured PostgreSQL database and use disposable test schemas. Model artifacts go under `data/cache/`; evaluation outputs go under `reports/`. Keep generated caches out of Git. If you change the seed or forecasting implementation, invalidate its generated cache before comparing results. On a machine with many CPU cores, set `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1` to avoid excessive numerical-library thread allocation; the startup helper sets conservative defaults.

The ordinary test suite forces the assistant offline and does not spend provider allowance. If Windows denies access to its global pytest temporary directory, pass a fresh workspace-local `--basetemp` path. Never use a folder containing user files for this option.

### Live plan discussion

Set `SCOOP_LLM_PROVIDER=gemini` in the ignored `.env` and provide `GEMINI_API_KEY` in the server process environment, then restart the API. The default model is `gemini-4-argon`. After a new plan's mechanical scan, the assistant chooses additional catalog-intersection and operational queries, then saves an evidence-based weekly report and specific questions. Existing plans expose an explicit Explore this week action. Default limits are 120 provider calls and a conservative US$3 estimated allowance for this demo. Opening the conversation reads its saved report without repeating the exploration. See [assistant configuration and behavior](docs/ASSISTANT.md).

Optional report figures: install `matplotlib==3.11.2` in a reporting environment and run `python scripts/plot-evaluation.py`. Figure sources and PNG/SVG outputs are included.

## What to demonstrate

1. Review a weekly finding, its observed-versus-expected chart and alternative explanations.
2. Open the assistant's topic list, discuss the evidence, and record interpretations. Continue to the next stage when ready.
3. Choose purchasing directions, district scopes and the operational objective; review the proposed watch list before approval.
4. Inspect supplier dates, protection-window forecasts, capacity cuts and case quantities. Confirm a synthetic order and export CSV.
5. Add or edit a watch, reload, and inspect persisted decisions and chat context. A new week carries unresolved watches forward and shows the previous week's dated recap.
6. Use Settings to switch simulation data and week, revisit saved progress, or reset the current simulation.

See [the demo guide](docs/DEMO.md) for a walkthrough. Historical inventory is a generated snapshot; confirming a demo order does not retroactively simulate physical warehouse movements.

## Design and evidence

- [System design and technical document](docs/TECHNICAL_DESIGN.md)
- [Product and modelling decisions](DECISIONS.md)
- [Algorithm implementation and evaluation notes](docs/ALGORITHM_NOTES.md)
- [AI, data and dependency disclosure](docs/THIRD_PARTY.md)

The forecast, detector and capacity allocator are evaluated separately. A requested service level is not a measured fill-rate guarantee. The capacity heuristic is conservative rather than globally optimal. Synthetic results establish reproducibility and expose weaknesses; they do not establish operational savings for a real retailer.

## Repository layout

```text
backend/scoop/synth/       Synthetic catalog and operational history
backend/scoop/algorithms/ Forecast, monitoring and replenishment
backend/scoop/ai/         Evidence investigator, Gemini tools and offline fallback
backend/scoop/api/        HTTP views, validation and persisted actions
backend/tests/            Focused regression and API tests
frontend/                 React + TypeScript planner
reports/                  Reproducible evaluation outputs
docs/                     Design, demo and disclosure
scripts/                  Local Windows runtime helpers
```

## Submission status

The implementation branch is `claude/scoop-prototype`. Publication, main-branch promotion and competition submission remain owner-controlled. The team must confirm its Team ID, roster, contribution declaration and public release before using the documents as a final submission. No sponsor-provided data or conversation exports belong in the public repository.
