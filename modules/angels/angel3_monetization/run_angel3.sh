#!/bin/bash
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 angel3_monetization.py "$@"
