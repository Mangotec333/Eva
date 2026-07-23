#!/bin/bash
# Weekly retro entrypoint for launchd (com.eva.retro-agent).
# Runs one Weekly Retro Digest headless (reads eva-state + the retro log,
# persists the digest, emits it back to eva-state) and prints the narrative.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 main.py --run-once "$@"
