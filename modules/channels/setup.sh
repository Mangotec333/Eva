#!/usr/bin/env bash
# EVA Channels — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Channels — multi-platform publish (Reddit + Substack)"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_CHANNELS_PORT:-8781}"
HOST="${EVA_CHANNELS_HOST:-0.0.0.0}"

echo "==> Starting EVA Channels on ${HOST}:${PORT} ..."
echo "==> Dashboard: http://localhost:${PORT}/"
echo "==> API docs:  http://localhost:${PORT}/docs"
echo "==> Health:    http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
