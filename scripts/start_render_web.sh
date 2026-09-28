#!/bin/sh
# Render's free plan does not offer a separate background-worker service.
# Run the database-backed worker alongside FastAPI in the single free web
# container.  Run data lives in Postgres, so no shared local volume is needed.
set -eu

python -m runs.worker &
worker_pid=$!

cleanup() {
  kill "$worker_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!
wait "$api_pid"
