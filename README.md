# Scoop

Scoop is a weekly planning tool for the planner who restocks a distribution centre's cold store. It forecasts demand until the next delivery, spots changes early, finds which products are moving, and drafts an order that fits the cold store. An AI assistant writes the weekly report, answers questions and takes in the planner's context.

The live demo is at [scoopplanner.com](https://scoopplanner.com). This repository holds the full prototype, built for the Corporate Link Challenge 2026.

## What is in the demo

The demo runs on a synthetic world: one cold store with 62 pallets of space, 20 stores in four districts, 75 ice-cream products and eight suppliers, with daily history from April to August 2026. It opens on Monday 27 July 2026. A quieter week (22 June) can be chosen in Settings.

The planner works through three steps each week:

1. **Report** – what changed in demand and why, with the data behind each finding.
2. **Orders** – a recommended order for every product, with the calculation behind each line; edit and approve.
3. **Watch** – a dashboard of stock, space and risks, with widgets for chosen products.

For the demo, two extra steps play the next two weeks forward (**Play**) and compare Scoop's order with a simple rule, the 28-day average plus 25% (**Results**). On first visit, **Start the tour** walks through all of it.

## Run it locally

You need Python 3.12+, PostgreSQL 16 or 17, Node.js 22+ and pnpm. Docker Compose can provide PostgreSQL.

From the repository root:

```sh
docker compose up -d db
python -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
export PYTHONPATH=backend            # Windows: $env:PYTHONPATH = 'backend'
cp .env.example .env
python -m pip install -r backend/requirements-dev.txt
python -m scoop.synth.load           # loads the synthetic world (replaces the demo tables)
python -m scoop.prepare_demo         # builds the 27 July plan; no LLM call
bash start.sh                        # builds the frontend and serves the app and API
```

Open http://127.0.0.1:8008. `PORT=8009 bash start.sh` uses another port, and `bash start.sh --help` lists the options. Restarting the app keeps the demo's progress; **Settings → Reset** returns to the start of the week.

On Windows without Docker, `scripts/setup-local.ps1 -LoadData` sets up a local PostgreSQL database, loads the data and builds the plan; `scripts/start-db.ps1` and `scripts/start-app.ps1` start it again later. Pass `-Python` and `-PostgresBin` if your paths differ.

### AI assistant

The app works without an API key: the report is a list of the computed findings and a scripted assistant handles basic commands. For the live assistant, set `SCOOP_LLM_PROVIDER=gemini` in `.env` and `GEMINI_API_KEY` in the server environment, then restart. The key stays on the server. See [docs/ASSISTANT.md](docs/ASSISTANT.md).

### Deployment

scoopplanner.com runs from `deploy/`: a Docker image of the app, a dedicated PostgreSQL database and persistent caches, with the live assistant capped at 50 calls per day. See [deploy/README.md](deploy/README.md).

## Tests

```sh
python -m pytest backend/tests -q    # backend tests; the assistant is forced offline
pnpm --dir frontend build            # type check and production build
SCOOP_TEST_URL=http://127.0.0.1:8008 pnpm --dir frontend exec playwright test e2e/walkthrough.spec.ts
```

Backend tests need PostgreSQL and use disposable schemas. `python -m scoop.evaluate` runs the offline evaluation; outputs go to `reports/`.

## Project layout

| Path | Contents |
| --- | --- |
| `backend/scoop/algorithms/` | Forecast (LightGBM), early warnings (CUSUM), trend finder, order calculation |
| `backend/scoop/ai/` | Weekly report, assistant tools and number checks |
| `backend/scoop/api/` | FastAPI routes |
| `backend/scoop/synth/` | Synthetic world generator |
| `frontend/src/` | React and TypeScript web app |
| `frontend/e2e/` | Browser tests |
| `scripts/` | Tour bundle builder, evaluation and local setup scripts |

## Further reading

- [Algorithm notes](docs/ALGORITHM_NOTES.md)
- [Assistant](docs/ASSISTANT.md)
- [Demo guide](docs/DEMO.md)
- [AI, data and third-party disclosure](docs/THIRD_PARTY.md)

All data is synthetic, and product, brand, store and supplier names are fictional.
