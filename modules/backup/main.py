"""
EVA Backup — FastAPI microservice
=================================
Port: 8793

Periodically (via /backup/tick, cron-safe/idempotent) tars+gzips every module's
local SQLite files and uploads the archive to a Google Drive folder, keeping the
newest N archives (retention). Drive is the single network chokepoint; offline by
default (StubDriveClient) so nothing real fires in tests.

Endpoints:
  GET  /health         Health + config (drive impl, folder, retention)
  POST /backup/tick    Run one backup cycle (scan -> archive -> upload -> retain)
  GET  /backup/status  Config + last run + archives currently in Drive
  GET  /backup/ledger  Append-only audit trail (?event_type=&limit=)

Go-live: same ``~/.eva/drive_credentials.json`` as meet-ingest, plus
``EVA_BACKUP_DRIVE_FOLDER_ID`` and ``EVA_BACKUP_DRIVE=real``.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from service import BackupService

AGENT_VERSION = "0.1.0"
PORT = 8793

service = BackupService()

app = FastAPI(
    title="EVA Backup",
    description=(
        "Periodic backup of every module's local SQLite files to Google Drive "
        "with simple retention. Idempotent, cron-safe, offline-testable."
    ),
    version=AGENT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-backup",
        "version": AGENT_VERSION,
        "port": PORT,
        "drive": service.drive.name,
        "folder_configured": bool(service.folder_id),
        "retention": service.retention,
    }


@app.post("/backup/tick", tags=["Backup"])
async def backup_tick():
    """Run one backup cycle. Never raises — failures come back as ok=False."""
    return service.tick(actor="http")


@app.get("/backup/status", tags=["Backup"])
async def backup_status():
    """Config + last run + archives currently in Drive."""
    return service.status()


@app.get("/backup/ledger", tags=["Backup"])
async def backup_ledger(event_type: Optional[str] = None, limit: int = 100):
    """Append-only audit trail of backups + retention deletes."""
    return {"events": service.store.query_ledger(event_type=event_type, limit=limit)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Backup service")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
