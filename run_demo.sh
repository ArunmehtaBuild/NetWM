#!/usr/bin/env bash
# NetWM dashboard, one-command launch (Linux / macOS); the Windows equivalent is run_demo.bat.
# Run from the repository with the venv active. Ctrl+C stops both servers.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python}"

echo "[1/4] Syncing API fixtures to the frontend mock store..."
"$PY" scripts/sync_fixtures.py

echo "[2/4] Starting the NetWM FastAPI backend on 127.0.0.1:5000..."
"$PY" -m uvicorn backend.server:app --host 127.0.0.1 --port 5000 &
API_PID=$!

echo "[3/4] Starting the dashboard on 127.0.0.1:8080..."
"$PY" -m http.server 8080 --directory frontend --bind 127.0.0.1 >/dev/null 2>&1 &
WEB_PID=$!
trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null' EXIT INT TERM

echo "[4/4] Waiting for the backend to be ready..."
# a cold start imports torch and takes ~8 s; opening the browser earlier shows the mock fallback
"$PY" backend/wait_ready.py --timeout 45

URL=http://127.0.0.1:8080
if command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1 || true
elif command -v open >/dev/null; then open "$URL" || true; fi

echo
echo "NetWM is running offline:"
echo "  - Backend API:  http://127.0.0.1:5000/docs"
echo "  - Dashboard:    $URL"
echo "Press Ctrl+C to stop."
wait
