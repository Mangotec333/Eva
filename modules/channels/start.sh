#!/bin/bash
cd "$(dirname "$0")"
source ~/.zshrc 2>/dev/null || true
uvicorn channels_api:app --host 0.0.0.0 --port 8770 --reload
