#!/bin/bash
# Monthly App Category Scan entrypoint for launchd (com.eva.trend-agent-appscan).
#
# The engine here is deterministic aggregation only (see app_scan_engine.py) —
# it does NOT do the web research itself. Each month, the fresh top-10-per-
# category research (with sources) must be supplied as a case JSON before this
# runs, produced upstream by a Perplexity / EVA research subagent pass, e.g.:
#   cases/app_scan_YYYY-MM.json
#
# This wrapper picks the current month's case file by convention and runs it
# through the CLI, printing the aggregated report + flags.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"

CASE_FILE="cases/app_scan_$(date +%Y-%m).json"

if [ ! -f "$CASE_FILE" ]; then
    echo "[trend-agent] No case file found at $CASE_FILE." >&2
    echo "[trend-agent] Run the upstream research pass first (Perplexity wide-search across venture-aligned categories) and save it to $CASE_FILE, then re-run this script." >&2
    exit 1
fi

python3 cli.py app-scan "$CASE_FILE"
