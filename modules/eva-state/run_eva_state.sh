#!/bin/bash
# Long-running HTTP entrypoint for launchd (com.eva.eva-state).
# Runs the governed State Ledger microservice on port 8769.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 main.py "$@"
