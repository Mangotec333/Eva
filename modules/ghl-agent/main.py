"""
EVA GHL Agent — FastAPI microservice
====================================
Port: 8782

The single Eva-owned service that talks to GoHighLevel. It does two things:

  Part 1 — one-time campaign/funnel build (idempotent, API-driven).
  Part 2 — the ongoing lead-capture automation loop.

Endpoints:
  GET  /health          Health + last-run summary + lead-event count
  GET  /directive       Current live directive (directive.md)
  POST /lead/capture    Upsert a GHL contact, tag, pipeline, campaign enroll
  POST /lead/webhook    Receive GHL events -> lead lifecycle -> state ledger
  GET  /funnel/status   Whether the one-time build exists
  POST /funnel/build    Trigger the Part 1 build (idempotent)

Offline by default in the sandbox (stub GHL + stub state client); set
``GHL_ACCESS_TOKEN`` to talk to live GoHighLevel, or ``EVA_GHL_OFFLINE=1`` to
force stubs.
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from ghl_client import is_offline
from service import CaptureError, GHLAgentService

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")
AGENT_VERSION = "0.1.0"
PORT = 8782

service = GHLAgentService()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _directive_version() -> str:
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip().lower().startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass
    return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory.init_db(service.db_path)
    yield


app = FastAPI(
    title="EVA GHL Agent",
    description=(
        "The single Eva-owned GoHighLevel integration: a one-time, idempotent "
        "campaign/funnel build and the ongoing lead-capture automation loop. "
        "Lead lifecycle events flow to the Eva State Ledger."
    ),
    version=AGENT_VERSION,
    lifespan=lifespan,
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
    run = memory.latest_run(service.db_path)
    return {
        "status": "ok",
        "module": "eva-ghl-agent",
        "version": AGENT_VERSION,
        "port": PORT,
        "db": service.db_path,
        "directive_version": _directive_version(),
        "offline": is_offline(),
        "lead_event_count": memory.lead_event_count(service.db_path),
        "last_run": {
            "at": run["timestamp"] if run else None,
            "kind": run["kind"] if run else None,
            "outputs": run["outputs"] if run else None,
        },
    }


@app.get("/directive", response_class=PlainTextResponse, tags=["Meta"])
async def get_directive():
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


# ---------------------------------------------------------------------------
# Part 1 — funnel build
# ---------------------------------------------------------------------------

@app.post("/funnel/build", tags=["Funnel"])
async def funnel_build():
    """Trigger the idempotent one-time build. Returns created/skipped/manual."""
    return service.build_funnel()


@app.get("/funnel/status", tags=["Funnel"])
async def funnel_status():
    """Whether the pipeline, calendar, custom field, templates, workflow exist."""
    return service.funnel_status()


# ---------------------------------------------------------------------------
# Part 2 — lead-capture loop
# ---------------------------------------------------------------------------

@app.post("/lead/capture", tags=["Lead"])
async def lead_capture(body: dict = Body(..., description="{email, name?, phone?, source?}")):
    """Upsert a GHL contact and drop it into the acquisition funnel."""
    email = (body.get("email") or "").strip()
    phone = (body.get("phone") or "").strip()
    if not email and not phone:
        raise HTTPException(status_code=422, detail="email or phone is required")
    try:
        return service.capture_lead(
            email=email, phone=phone,
            name=(body.get("name") or "").strip(),
            source=(body.get("source") or "eva-acquisition").strip())
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/lead/webhook", tags=["Lead"])
async def lead_webhook(event: dict = Body(..., description="A GHL webhook event")):
    """Receive a GHL event, map it to a lead lifecycle event, write both ledgers."""
    return service.handle_webhook(event)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA GHL Agent microservice")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
