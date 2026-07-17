#!/usr/bin/env bash
# EVA Health Monitor — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Health Monitor — cross-module /health watchdog + alerting"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_HEALTH_MONITOR_PORT:-8788}"
HOST="${EVA_HEALTH_MONITOR_HOST:-0.0.0.0}"

echo ""
echo "==> Monitored modules come from config.py (override with EVA_HEALTH_MONITOR_CONFIG"
echo "    -> path to a JSON list of {\"name\",\"url\"}). Alert threshold:"
echo "    EVA_HEALTH_FAILURE_THRESHOLD (default 3 consecutive down ticks)."
echo ""
echo "==> Starting EVA Health Monitor on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
