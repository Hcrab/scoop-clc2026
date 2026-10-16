#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

usage() {
  cat <<'EOF'
Usage: bash start.sh

Build the frontend and run Scoop using the existing database and Python environment.
Complete the first-time setup in README.md before running this script.

Environment:
  PORT    HTTP port (default: 8008)
  HOST    Listen address (default: 127.0.0.1)
  PYTHON  Python executable (default: this repository's .venv)

Example: PORT=8009 bash start.sh
Stop with Ctrl+C.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if (( $# )); then
  usage >&2
  exit 1
fi

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON="$PWD/.venv/bin/python"
  elif [[ -x .venv/Scripts/python.exe ]]; then
    PYTHON="$PWD/.venv/Scripts/python.exe"
  else
    echo "Python environment missing. Complete the first-time setup in README.md." >&2
    exit 1
  fi
fi

export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

echo "Checking database..."
"$PYTHON" - <<'PY'
import sys

sys.path.insert(0, "backend")
from sqlalchemy import text
from scoop.db import engine

try:
    with engine.connect() as connection:
        ready = connection.execute(text("SELECT to_regclass('public.settings')")).scalar()
except Exception:
    sys.exit("Cannot connect to PostgreSQL. Start your database, then run start.sh again.")
if ready is None:
    sys.exit("Demo data is missing. Complete the first-time setup in README.md.")
PY

if command -v pnpm >/dev/null 2>&1; then
  PNPM=pnpm
elif command -v pnpm.cmd >/dev/null 2>&1; then
  PNPM=pnpm.cmd
else
  echo "pnpm is missing. Install pnpm and Node.js 22+; see README.md." >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  "$PNPM" --dir frontend install --frozen-lockfile
fi
"$PNPM" --dir frontend build

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8008}"
echo "Starting Scoop at http://$HOST:$PORT"
exec "$PYTHON" -m uvicorn scoop.main:app --app-dir backend --host "$HOST" --port "$PORT"
