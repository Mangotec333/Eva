#!/bin/bash
# Monthly Competitor Scan entrypoint for launchd (com.eva.trend-agent-competitorscan).
#
# Unlike run_app_scan.sh this is fully self-contained: no upstream research pass
# is needed. Step 1 is a plain HTTP fetch of the AI-agent directory, step 2 is a
# deterministic diff against the previous month's snapshot. There is no LLM call
# in either step, so a run costs ~$0 in ongoing credits.
#
# If the fetch fails (site down, layout changed, zero cards parsed) it exits
# non-zero WITHOUT writing an empty snapshot, and the diff is skipped — an empty
# month would fake a mass exit now and a mass ALERT next month.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"

SNAPSHOT="cases/competitor_scan_$(date -u +%Y-%m).json"

if ! python3 competitor_fetch.py; then
    echo "[trend-agent] competitor-fetch failed; skipping the diff so a bad snapshot cannot produce a false verdict." >&2
    exit 1
fi

python3 cli.py competitor-scan "$SNAPSHOT"
