#!/usr/bin/env bash
# EVA Projects — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Projects — collapsible mind-map roadmap tracker"
echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Seeding the roadmap (idempotent) ..."
python cli.py seed || true

PORT="${EVA_PROJECTS_PORT:-8779}"
HOST="${EVA_PROJECTS_HOST:-0.0.0.0}"

echo "==> Starting EVA Projects on ${HOST}:${PORT} ..."
echo "==> Mind map: http://localhost:${PORT}/"
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
