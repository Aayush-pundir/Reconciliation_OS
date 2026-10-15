#!/usr/bin/env bash
# One-command local dev launcher: sets up (if needed) and runs both the
# backend and frontend together from a single terminal, no Docker required.
#
# Usage:
#   ./run-local.sh
#
# Ctrl+C in this terminal stops both the frontend and the backend.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT=7400
FRONTEND_PORT=7401

echo "== Backend setup =="
cd "$SCRIPT_DIR/backend"

if [ ! -d .venv ]; then
  echo "Creating Python venv..."
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

export JOB_RUNNER=inprocess
export DATABASE_URL="sqlite:///./recon_os.db"

alembic upgrade head

echo "Starting backend on http://localhost:$BACKEND_PORT ..."
uvicorn app.main:app --reload --port "$BACKEND_PORT" > "$SCRIPT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
CLEANED_UP=0

cleanup() {
  if [ "$CLEANED_UP" -eq 1 ]; then
    return
  fi
  CLEANED_UP=1
  echo ""
  echo "Stopping backend (pid $BACKEND_PID)..."
  # uvicorn's --reload supervisor responds to SIGINT (the same signal a
  # real Ctrl+C sends) but has been observed to ignore a plain SIGTERM
  # and keep the port held open - so SIGINT first, then escalate.
  kill -INT "$BACKEND_PID" 2>/dev/null || true
  for i in 1 2 3 4 5; do
    kill -0 "$BACKEND_PID" 2>/dev/null || return
    sleep 1
  done
  kill -TERM "$BACKEND_PID" 2>/dev/null || true
  sleep 1
  kill -0 "$BACKEND_PID" 2>/dev/null && kill -KILL "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Waiting for backend to come up..."
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
    echo "Backend is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Backend did not come up in time - check backend.log"
    exit 1
  fi
  sleep 1
done

echo ""
echo "== Frontend setup =="
cd "$SCRIPT_DIR/frontend"

if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

echo ""
echo "Backend:  http://localhost:$BACKEND_PORT/docs"
echo "Frontend: http://localhost:$FRONTEND_PORT  (opening shortly)"
echo "Press Ctrl+C here to stop both."
echo ""

npm run dev
