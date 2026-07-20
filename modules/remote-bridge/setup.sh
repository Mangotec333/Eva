#!/usr/bin/env bash
# EVA Remote-Bridge — setup and launch script (the ONE authenticated front door)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Remote-Bridge — authenticated remote instruction channel"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${REMOTE_BRIDGE_PORT:-8795}"
HOST="${REMOTE_BRIDGE_HOST:-0.0.0.0}"

if [ -z "${REMOTE_BRIDGE_API_KEY:-}" ]; then
  echo ""
  echo "!! WARNING: REMOTE_BRIDGE_API_KEY is not set."
  echo "!! The service will FAIL CLOSED — every /remote/* route returns 503 until"
  echo "!! you configure a key. Set it (in ~/.eva/*.json, ~/.zshrc, or the launchd"
  echo "!! plist EnvironmentVariables — NEVER commit it) before exposing a tunnel."
  echo ""
fi

echo "==> Starting EVA Remote-Bridge on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
