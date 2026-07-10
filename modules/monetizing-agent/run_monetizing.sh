#!/bin/bash
# Weekly scan entrypoint for launchd (com.eva.monetizing).
# Runs the governed Monetizing Agent's revenue-leak scan and prints the brief.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 cli.py scan "$@"
