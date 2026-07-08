#!/usr/bin/env bash
# EVA LinkedIn Analytics — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA LinkedIn Analytics — read + store LinkedIn post analytics"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_LINKEDIN_ANALYTICS_PORT:-8780}"
HOST="${EVA_LINKEDIN_ANALYTICS_HOST:-0.0.0.0}"

echo "==> Starting EVA LinkedIn Analytics on ${HOST}:${PORT} ..."
echo "==> Dashboard: http://localhost:${PORT}/"
echo "==> API docs:  http://localhost:${PORT}/docs"
echo "==> Health:    http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
