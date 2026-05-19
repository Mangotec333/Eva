#!/bin/zsh
# EVA Knowledge OS — launcher
# Sources .zshrc for PATH / env, then starts the API on port 8771.

source "$HOME/.zshrc" 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[EVA Knowledge OS] Starting on port 8771..."
uvicorn knowledge_api:app \
  --host 0.0.0.0 \
  --port 8771 \
  --reload \
  --log-level info
