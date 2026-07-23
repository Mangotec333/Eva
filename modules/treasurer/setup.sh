#!/usr/bin/env bash
# EVA Treasurer — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Treasurer — personal/business finance module"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_TREASURER_PORT:-8794}"
HOST="${EVA_TREASURER_HOST:-0.0.0.0}"

echo "==> Starting EVA Treasurer on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo "==> Summary:  http://localhost:${PORT}/summary"
echo ""

exec uvicorn main:app --host "$HOST" --port "$PORT"
