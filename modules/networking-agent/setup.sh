#!/usr/bin/env bash
# EVA Networking-Agent (Relationship Capital + Community Scout) — setup and launch
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Networking-Agent — Relationship Capital + Community Scout"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_NETWORKING_PORT:-8793}"
HOST="${EVA_NETWORKING_HOST:-0.0.0.0}"

echo "==> Starting EVA Networking-Agent on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Status:   http://localhost:${PORT}/status"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
