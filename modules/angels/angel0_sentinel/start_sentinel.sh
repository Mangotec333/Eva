#!/bin/bash
# Sentinel — start or restart
# Called by launchd every 5 minutes (StartInterval 300)

source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 sentinel.py
