#!/usr/bin/env bash
# Runs the AskMyDoc backend (FastAPI, :8000) and frontend (Next.js, :3000) in one terminal.
# Output is prefixed per server. Ctrl+C stops both; if either server exits, the other stops too.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Kill every process started by this script (the whole process group) on exit.
trap 'trap - EXIT INT TERM; kill 0 2>/dev/null' EXIT INT TERM

.venv/bin/uvicorn backend.main:app --reload 2>&1 | sed -u 's/^/[backend]  /' &
(cd frontend && npm run dev) 2>&1 | sed -u 's/^/[frontend] /' &

wait -n
