#!/usr/bin/env bash
# EVA Meet Ingest — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Meet Ingest — Google Meet -> Drive -> local whisper.cpp transcripts"
echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "==> Runtime prerequisites (user-provided; NOT installed by pip):"

# ffmpeg — audio extraction (expected preinstalled on the Eva host).
if command -v ffmpeg >/dev/null 2>&1; then
    echo "    [ok]   ffmpeg found: $(command -v ffmpeg)"
else
    echo "    [MISSING] ffmpeg not found — install it (brew install ffmpeg / apt install ffmpeg)."
fi

# whisper.cpp binary + ggml model — local, zero-API-cost transcription.
WHISPER_BIN="${EVA_WHISPER_BIN:-$HOME/.eva/whisper/main}"
WHISPER_MODEL="${EVA_WHISPER_MODEL:-$HOME/.eva/whisper/ggml-base.en.bin}"
if [ -x "$WHISPER_BIN" ]; then
    echo "    [ok]   whisper.cpp binary: $WHISPER_BIN"
else
    echo "    [MISSING] whisper.cpp binary at $WHISPER_BIN"
    echo "             Build it: https://github.com/ggerganov/whisper.cpp  (set EVA_WHISPER_BIN)"
fi
if [ -f "$WHISPER_MODEL" ]; then
    echo "    [ok]   whisper.cpp model:  $WHISPER_MODEL"
else
    echo "    [MISSING] ggml model at $WHISPER_MODEL"
    echo "             Download one (e.g. ggml-base.en.bin) (set EVA_WHISPER_MODEL)"
fi

# Drive OAuth credentials.
CREDS="$HOME/.eva/drive_credentials.json"
if [ -f "$CREDS" ]; then
    echo "    [ok]   Drive OAuth credentials: $CREDS"
else
    echo "    [MISSING] Drive OAuth credentials at $CREDS"
    echo "             Download an OAuth client_secret.json from Google Cloud and save it there."
fi

echo ""
echo "==> These prerequisites are checked at runtime with a clear error; the"
echo "    service never silently stubs them in production mode."
echo ""

PORT="${EVA_MEET_INGEST_PORT:-8785}"
HOST="${EVA_MEET_INGEST_HOST:-0.0.0.0}"

echo "==> Starting EVA Meet Ingest on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
