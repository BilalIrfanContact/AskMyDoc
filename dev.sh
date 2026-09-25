#!/usr/bin/env bash
# Runs the AskMyDoc backend (FastAPI, :8000) and frontend (Next.js, :3000) in one terminal.
# Output is prefixed per server. Ctrl+C stops both; if either server exits, the other stops too.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Give each server pipeline its own process group, including its child processes.
set -m
backend_pid=
frontend_pid=
cleanup() {
  if [[ -n "$backend_pid" ]]; then
    kill -TERM -- "-$backend_pid" 2>/dev/null || true
  fi
  if [[ -n "$frontend_pid" ]]; then
    kill -TERM -- "-$frontend_pid" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_backend() {
  .venv/bin/uvicorn backend.main:app --reload 2>&1 | sed -u 's/^/[backend]  /'
}
run_frontend() {
  (cd frontend && npm run dev) 2>&1 | sed -u 's/^/[frontend] /'
}
run_backend &
backend_pid=$!
run_frontend &
frontend_pid=$!

# Bash 3.2 (the system Bash on macOS) does not support wait -n.
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done
if ! kill -0 "$backend_pid" 2>/dev/null; then
  wait "$backend_pid"
else
  wait "$frontend_pid"
fi
