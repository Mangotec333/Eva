#!/usr/bin/env bash
# EVA Shopify — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Shopify — order sync + inventory + dropship fulfillment"
echo "==> Installing dependencies..."
pip install -r requirements.txt

PORT="${EVA_SHOPIFY_PORT:-8788}"
HOST="${EVA_SHOPIFY_HOST:-0.0.0.0}"

echo "==> Starting EVA Shopify on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""
echo "    Runs in offline stub mode until you supply a store domain + Admin API"
echo "    token (see README.md). Live writes are approval-gated."
echo ""

exec python main.py --host "$HOST" --port "$PORT"
