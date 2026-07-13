#!/bin/bash
echo "Setting up EVA Media Editor..."
pip install -r requirements.txt -q
command -v ffmpeg >/dev/null 2>&1 || echo "WARNING: ffmpeg not found — run: brew install ffmpeg"
echo "Starting Media Editor on port ${MEDIA_EDITOR_PORT:-8783}..."
python3 main.py
