#!/bin/bash
echo "Setting up EVA Video Generator..."
pip install -r requirements.txt -q
command -v ffmpeg >/dev/null 2>&1 || echo "WARNING: ffmpeg not found — run: brew install ffmpeg"
echo "Starting Video Generator on port ${VIDEO_GEN_PORT:-8784}..."
python3 main.py
