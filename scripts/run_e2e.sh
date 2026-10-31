#!/usr/bin/env bash
# Tayf Studio — one-command E2E proof: backend + frontend + real browser loop.
# Usage: scripts/run_e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-/home/z/my-project/venv/bin}"
RUN="$(mktemp -d /tmp/tayf-e2e-XXXX)"
export DATABASE_URL="sqlite:///$RUN/e2e.db"
export LOCAL_STORAGE_DIR="$RUN/storage"
export JWT_SECRET="e2e-only-secret-0123456789abcdef0123456789abcdef"
export AI_PROVIDER="${AI_PROVIDER:-mock}"

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "== migrations =="
(cd "$ROOT/backend" && "$VENV/python" -m alembic upgrade head >/dev/null)

echo "== backend :8000 =="
(cd "$ROOT/backend" && exec "$VENV/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

echo "== frontend :5173 =="
(cd "$ROOT/frontend" && exec npx vite --port 5173 --strictPort) &
FRONTEND_PID=$!

for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null || { echo "backend failed to boot"; exit 1; }
for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1 && break
  sleep 0.5
done

echo "== browser smoke =="
"$VENV/python" "$ROOT/scripts/e2e_smoke.py" http://127.0.0.1:5173 /tmp/tayf-unified-e2e.png
