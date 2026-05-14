#!/usr/bin/env bash
# EVA Deal Scout — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Deal Scout — Module 3"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_DEAL_SCOUT_PORT:-8766}"
HOST="${EVA_DEAL_SCOUT_HOST:-0.0.0.0}"

echo "==> Starting EVA Deal Scout on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
