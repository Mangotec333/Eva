"""
EVA Meet Ingest — FastAPI microservice
======================================
Port: 8785  (postcards 8778, projects 8779, linkedin-analytics 8780,
             channels 8781, ghl-agent 8782, media-editor 8783)

Frugal, self-hosted meeting pipeline: Google Meet auto-records to Drive -> EVA
polls Drive -> downloads -> extracts audio (ffmpeg) -> transcribes locally with
whisper.cpp (zero API cost) -> stores transcript + summary stub -> files them
into ``EVA/Meetings/<name>/``. All transports (Drive, transcription) sit behind
Protocols with offline stubs; v1 makes no network call under the stub transports.

Endpoints (spec section 5):
  GET    /health                 Status + last poll/process summary
  POST   /poll                   Discover new Drive recordings (idempotent)
  POST   /process/{meeting_id}   Run the pipeline for one meeting
  POST   /tick                   poll + process all pending (cron-safe)
  GET    /meetings               List meetings (optional ?status=)
  GET    /meetings/{id}          Get a meeting
  GET    /ledger                 Query the append-only ledger
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import database as db
from models import HealthResponse, PollRequest, ProcessRequest, TickRequest
from service import MeetIngestService, NotFoundError

VERSION = "1.0.0"

service = MeetIngestService()

app = FastAPI(
    title="EVA Meet Ingest",
    description=(
        "Frugal, self-hosted Google Meet -> Drive -> local whisper.cpp transcript "
        "pipeline with an append-only ledger. Zero API cost."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn):
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    return HealthResponse(
        status="ok",
        module="eva-meet-ingest",
        version=VERSION,
        db=db.DB_PATH,
        drive=service.drive.name,
        transcriber=service.transcriber.name,
        last_run=service.last_run(),
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@app.post("/poll", tags=["Pipeline"])
def poll(payload: PollRequest = PollRequest()):
    return _handle(lambda: service.poll(actor=payload.actor))


@app.post("/process/{meeting_id}", tags=["Pipeline"])
def process(meeting_id: str, payload: ProcessRequest = ProcessRequest()):
    return _handle(lambda: service.process(meeting_id, actor=payload.actor))


@app.post("/tick", tags=["Pipeline"])
def tick(payload: TickRequest = TickRequest()):
    return _handle(lambda: service.tick(actor=payload.actor))


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

@app.get("/meetings", tags=["Meetings"])
def list_meetings(status: Optional[str] = Query(default=None)):
    rows = service.list_meetings(status=status)
    return {"meetings": rows, "count": len(rows)}


@app.get("/meetings/{meeting_id}", tags=["Meetings"])
def get_meeting(meeting_id: str):
    return _handle(lambda: service.get_meeting(meeting_id))


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@app.get("/ledger", tags=["Ledger"])
def query_ledger(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
):
    rows = service.query_ledger(from_ts=from_, to_ts=to, event_type=event_type)
    return {"ledger": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Meet Ingest microservice")
    parser.add_argument("--port", type=int, default=8785, help="Port (default: 8785)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
