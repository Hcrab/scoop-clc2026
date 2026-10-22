# Scoop prototype server deployment

Application branch: `main`. Website: https://scoopplanner.com.
The existing HarbourFlow database and `/logistics/` site are independent.

Build `frontend/dist` locally with the pinned pnpm lockfile, then copy the
application, built frontend, `.dockerignore` and `deploy/` to `/opt/scoop`.
Keep credentials only in the ignored `/opt/scoop/deploy/.env` (mode 600):

```ini
SCOOP_DB_PASSWORD=<random alphanumeric password>
GEMINI_API_KEY=<server-only key>
SCOOP_LLM_PROVIDER=gemini
```

From `/opt/scoop`, first installation into the new, dedicated Scoop database:

```sh
docker compose -f deploy/compose.yaml build app
docker compose -f deploy/compose.yaml up -d db
docker compose -f deploy/compose.yaml run --rm app python -m scoop.synth.load
docker compose -f deploy/compose.yaml run --rm app python -m scoop.prepare_demo
docker compose -f deploy/compose.yaml up -d app
```

`synth.load` replaces Scoop demo tables. Do not run it during ordinary updates.
The current release uses the owner's already-validated local `public` database
and `seed93-monthly-issued-v2` cache, rather than regenerating the data. Export
with `pg_dump -n public --no-owner --no-acl -Fc`; restore into the dedicated
Scoop database while the app is stopped. Preserve the cloud usage ledger when
copying model caches. The saved report and tour mechanics remain unchanged.

Updates only rebuild and restart `app`. PostgreSQL and the model/usage cache use
named persistent volumes. A single API process owns the simulation queue.
The database has no public host port. Caddy on `nodelab_outbound` proxies to
`scoop-prototype:8008`; it manages HTTPS for the apex and `www` domain.

The paid model is `gemini-3.8-flash`. Every outbound model attempt, including
each report/tool-loop round, reserves one of **50 shared calls per Hong Kong
calendar day** before transmission. Failed/unknown outcomes count as attempts.
The persistent SQLite ledger uses an immediate write transaction, so concurrent
visitors cannot exceed the cap. Browser storage, Reset and restarts do not
reset the ledger. The original cumulative 120-call / US$3 estimated allowance
also remains in place; its environment settings can be adjusted separately.
No real supplier orders are transmitted.

Backup before modifying the deployed database:

```sh
mkdir -p backups
docker compose -f deploy/compose.yaml exec -T db pg_dump -U scoop -d scoop -Fc > backups/scoop.dump
```

Keep backups and credentials outside Git and public frontend assets.
