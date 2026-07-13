#!/bin/bash
# Long-running HTTP entrypoint for launchd (com.eva.media-editor).
# Runs the Media Editor microservice on port 8783 (MEDIA_EDITOR_PORT).
# ffmpeg must be on PATH (brew install ffmpeg). Fonts are bundled in assets/.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 main.py "$@"
