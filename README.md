# Scoop

Trend-aware ice-cream replenishment planning for the Corporate Link Challenge 2026.

Scoop helps a cold-store planner review preference signals, decide what to buy more or less of, and turn those decisions into case-level orders under supplier and warehouse constraints. The weekly flow is **Discover -> Direction -> Execute & watch**, with a persistent, explicitly scripted assistant.

The local prototype uses synthetic data: one DC, 20 stores, four districts, 60 SKUs and eight suppliers. Its default clock is **13 July 2026**. It requires no LLM API key and sends no real supplier orders.

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

Optional report figures: install `matplotlib==3.11.2` in a reporting environment and run `python scripts/plot-evaluation.py`. Figure sources and PNG/SVG outputs are included.

## What to demonstrate

1. Review a weekly finding, its observed-versus-expected chart and alternative explanations.
2. Record whether the evidence is persistent, one-off, weather-related, a data issue or uncertain.
3. Approve purchasing directions, district scopes and the operational objective.
4. Inspect supplier dates, protection-window forecasts, capacity cuts and case quantities. Confirm a synthetic order and export CSV.
5. Add a watch, reload, and inspect persisted decisions and chat context.

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
backend/scoop/ai/         Evidence investigator and scripted assistant
backend/scoop/api/        HTTP views, validation and persisted actions
backend/tests/            Focused regression and API tests
frontend/                 React + TypeScript planner
reports/                  Reproducible evaluation outputs
docs/                     Design, demo and disclosure
scripts/                  Local Windows runtime helpers
```

## Submission status

The implementation branch is `claude/scoop-prototype`. Publication, main-branch promotion and competition submission remain owner-controlled. The team must confirm its Team ID, roster, contribution declaration and public release before using the documents as a final submission. No sponsor-provided data or conversation exports belong in the public repository.
