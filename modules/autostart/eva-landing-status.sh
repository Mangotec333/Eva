#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Landing + Interest Status
#  Thin wrapper around modules/intelligence/landing_tracker.py:
#    1. landing liveness — HTTP status of the acquisition landing pages
#    2. lead-magnet interest — GHL contact counts per magnet tag
#
#  Runs like eva-status.sh. Sources the shell env first (same as the
#  ghl-agent) so GHL_ACCESS_TOKEN / GHL_LOCATION_ID are available; the
#  token is never hardcoded. Falls back to offline stub counts when no
#  token is present.
#
#  Usage:
#    ./eva-landing-status.sh            human-readable report
#    ./eva-landing-status.sh --text     morning-brief LANDING + INTEREST block
#    ./eva-landing-status.sh --json     machine-readable JSON
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

# Load GHL_ACCESS_TOKEN / GHL_LOCATION_ID the same way run_ghl_agent.sh does.
source ~/.zshrc 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACKER="$SCRIPT_DIR/../intelligence/landing_tracker.py"

if [ ! -f "$TRACKER" ]; then
    echo "landing_tracker.py not found at $TRACKER" >&2
    exit 1
fi

PY="$(command -v python3 || command -v python)"
exec "$PY" "$TRACKER" "$@"
