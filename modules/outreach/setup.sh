#!/usr/bin/env bash
# EVA Outreach & Investor Verification — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Outreach & Investor Verification — Module 6"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_OUTREACH_PORT:-8802}"
HOST="${EVA_OUTREACH_HOST:-0.0.0.0}"

echo "==> Starting EVA Outreach on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
