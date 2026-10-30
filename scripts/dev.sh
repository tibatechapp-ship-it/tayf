#!/usr/bin/env bash
# VisionForge Studio — dev process control (Termux / Linux, no Docker needed).
#   ./scripts/dev.sh start|stop|status|logs
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="${TMPDIR:-/tmp}"
API_LOG="$TMP/vf-api.log"
WEB_LOG="$TMP/vf-vite.log"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

wait_for() { # port label seconds
  local port="$1" label="$2" secs="${3:-25}" i=0
  while [ "$i" -lt "$((secs * 4))" ]; do
    port_busy "$port" && { echo "  ✔ $label ready on :$port"; return 0; }
    sleep 0.25; i=$((i + 1))
  done
  echo "  ✖ $label did not start on :$port" >&2; return 1
}

start() {
  if port_busy "$API_PORT"; then echo "API already on :$API_PORT"; else
    ( cd "$ROOT/backend" && setsid --fork python -m uvicorn app.main:app \
        --host 127.0.0.1 --port "$API_PORT" </dev/null >"$API_LOG" 2>&1 )
    wait_for "$API_PORT" "backend" || { tail -20 "$API_LOG"; exit 1; }
  fi

  if port_busy "$WEB_PORT"; then echo "Web already on :$WEB_PORT"; else
    ( cd "$ROOT/frontend" && setsid --fork npx vite --host 127.0.0.1 \
        --port "$WEB_PORT" --strictPort </dev/null >"$WEB_LOG" 2>&1 )
    wait_for "$WEB_PORT" "frontend" || { tail -20 "$WEB_LOG"; exit 1; }
  fi

  echo
  echo "  App       http://127.0.0.1:$WEB_PORT"
  echo "  API docs  http://127.0.0.1:$API_PORT/docs"
  echo "  Health    http://127.0.0.1:$WEB_PORT/api/v1/health"
}

stop() {
  pkill -f "[u]vicorn app.main:app" && echo "  ✔ backend stopped"
  pkill -f "[v]ite --host 127.0.0.1" && echo "  ✔ frontend stopped"
  return 0
}

status() {
  port_busy "$API_PORT" && echo "  backend  :$API_PORT  UP" || echo "  backend  :$API_PORT  down"
  port_busy "$WEB_PORT" && echo "  frontend :$WEB_PORT  UP" || echo "  frontend :$WEB_PORT  down"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  logs) tail -n "${2:-30}" "$API_LOG" "$WEB_LOG" 2>/dev/null ;;
  *) echo "usage: $0 start|stop|status|logs [n]" >&2; exit 2 ;;
esac
