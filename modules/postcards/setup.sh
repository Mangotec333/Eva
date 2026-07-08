#!/usr/bin/env bash
# EVA Postcards — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Postcards — quote-card content + LinkedIn auto-publish"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_POSTCARDS_PORT:-8778}"
HOST="${EVA_POSTCARDS_HOST:-0.0.0.0}"

echo "==> Starting EVA Postcards on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
