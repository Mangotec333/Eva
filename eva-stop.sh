#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  EVA SHUTDOWN SCRIPT
#  Stops all running EVA services.
# ─────────────────────────────────────────────

pkill -f "screenpipe" 2>/dev/null
pkill -f "eva_logger.py" 2>/dev/null
pkill -f "eva_context_api.py" 2>/dev/null
pkill -f "eva-deal-scout/main.py" 2>/dev/null

echo "EVA services stopped."
