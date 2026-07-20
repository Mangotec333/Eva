#!/bin/bash
# Long-running HTTP entrypoint for launchd (com.eva.video-generator).
# Runs the Video Generator microservice on port 8794 (VIDEO_GEN_PORT).
# ffmpeg must be on PATH (brew install ffmpeg). Fonts are bundled in assets/.
source ~/.zshrc 2>/dev/null || true
cd "$(dirname "$0")"
python3 main.py "$@"
