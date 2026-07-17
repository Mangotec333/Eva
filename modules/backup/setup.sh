#!/usr/bin/env bash
# EVA Backup — setup and launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> EVA Backup — periodic SQLite -> Google Drive archiver"
echo "==> Installing dependencies..."
pip install -r requirements.txt

# --- Go-live prerequisite checks (warn only; stub works offline) -----------
CREDS_PATH="${HOME}/.eva/drive_credentials.json"
if [ ! -f "$CREDS_PATH" ]; then
  echo "WARN: Drive OAuth creds not found at $CREDS_PATH"
  echo "      (same file meet-ingest uses). Real uploads need it; stub runs offline."
fi
if [ -z "${EVA_BACKUP_DRIVE_FOLDER_ID}" ]; then
  echo "WARN: EVA_BACKUP_DRIVE_FOLDER_ID is not set — real ticks will refuse to upload."
fi
if [ "${EVA_BACKUP_DRIVE}" != "real" ]; then
  echo "NOTE: EVA_BACKUP_DRIVE is not 'real' — using the offline StubDriveClient."
fi

PORT="${EVA_BACKUP_PORT:-8788}"
HOST="${EVA_BACKUP_HOST:-0.0.0.0}"

echo "==> Starting EVA Backup on ${HOST}:${PORT} ..."
echo "==> API docs: http://localhost:${PORT}/docs"
echo "==> Health:   http://localhost:${PORT}/health"
echo ""

exec python main.py --host "$HOST" --port "$PORT"
