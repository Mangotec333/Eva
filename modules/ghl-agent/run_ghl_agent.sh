#!/bin/bash
# Long-running HTTP entrypoint for launchd (com.eva.ghl-agent).
# Runs the governed GHL Agent microservice on port 8782.
# GHL_ACCESS_TOKEN / GHL_LOCATION_ID are read from the shell env (~/.zshrc / ~/.env).
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 main.py "$@"
