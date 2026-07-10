"""
EVA State Ledger — FastAPI microservice
=======================================
Port: 8769

The governed append-only state/history ledger — the single source of truth
across all Eva agents and surfaces. Kalpawriksha (the Project Map) and the
Command Center become VIEWS of this service, not independent stores.

Endpoints:
  GET  /health                    Health + last-run summary + event count
  GET  /directive                 Current live directive (directive.md)
  POST /events                    Append an event (immutable once written)
  GET  /events                    Filter events (project/track/entity_type/…/since)
  POST /events/{id}/correct       Write a correction_event superseding a prior event
  GET  /state/today               Priorities (blockers + deadlines + revenue proximity)
  GET  /state/projects            Current per-project status
  GET  /state/project-map         Kalpawriksha tree derived from the ledger
  GET  /state/pending-approvals   Unanswered approval requests
  GET  /state/recent-decisions    Recent decision_made events
  GET  /state/open-blockers       Standing blockers
  GET  /state/agent-health        Latest run per agent (cross-agent liveness)
  GET  /state/coined-terms        Coined terms w/ reference count, traction, engagement
  POST /admin/seed                Idempotent seed (Kalpawriksha import + lost state)
  POST /admin/render-map          Regenerate project_map.json (+ optional index.html)
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from service import NotFoundError, StateService

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")
AGENT_VERSION = "0.1.0"
PORT = 8769

service = StateService()


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
    title="EVA State Ledger",
    description=(
        "Governed append-only state/history ledger — the single source of truth "
        "across all Eva agents and surfaces. Kalpawriksha and the Command Center "
        "are views of it. Corrections are new events; nothing is edited or deleted."
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


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health_check():
    run = memory.latest_run(service.db_path)
    return {
        "status": "ok",
        "module": "eva-state",
        "version": AGENT_VERSION,
        "port": PORT,
        "db": service.db_path,
        "directive_version": _directive_version(),
        "event_count": memory.event_count(service.db_path),
        "last_run": {
            "at": run["timestamp"] if run else None,
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
# Events (append-only)
# ---------------------------------------------------------------------------

@app.post("/events", tags=["Events"])
async def append_event(body: dict = Body(..., description="Event fields")):
    """Append an event. Immutable once written; identity columns are frozen."""
    event_type = body.get("event_type")
    if not event_type:
        raise HTTPException(status_code=422, detail="event_type is required")
    allowed = {
        "event_type", "summary", "actor", "source_surface", "project", "track",
        "entity_type", "entity_id", "payload", "evidence_urls",
        "supersedes_event_id", "corrects_event_id", "confidence", "status",
        "timestamp",
    }
    kwargs = {k: v for k, v in body.items() if k in allowed}
    return service.record(**kwargs)


@app.get("/events", tags=["Events"])
async def list_events(
    project: Optional[str] = Query(None),
    track: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp lower bound"),
    limit: Optional[int] = Query(None),
):
    return service.events(
        project=project, track=track, entity_type=entity_type,
        entity_id=entity_id, event_type=event_type, actor=actor,
        since=since, limit=limit,
    )


@app.post("/events/{event_id}/correct", tags=["Events"])
async def correct_event(
    event_id: str = Path(..., description="Event to supersede"),
    body: dict = Body(default={}),
):
    """Write a correction_event that supersedes a prior event (never edits/deletes)."""
    summary = body.get("summary")
    if not summary:
        raise HTTPException(status_code=422, detail="summary is required for a correction")
    try:
        return service.correct(
            event_id, summary=summary,
            status=body.get("status", memory.STATUS_DROPPED),
            actor=body.get("actor", "Eva"),
            source_surface=body.get("source_surface", ""),
            payload=body.get("payload"),
            evidence_urls=body.get("evidence_urls"),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Derived state (the read surface for the Command Center)
# ---------------------------------------------------------------------------

@app.get("/state/today", tags=["State"])
async def state_today():
    return service.today()


@app.get("/state/projects", tags=["State"])
async def state_projects():
    return service.projects()


@app.get("/state/project-map", tags=["State"])
async def state_project_map():
    return service.project_map()


@app.get("/state/pending-approvals", tags=["State"])
async def state_pending_approvals():
    return service.pending_approvals()


@app.get("/state/recent-decisions", tags=["State"])
async def state_recent_decisions(limit: int = Query(20)):
    return service.recent_decisions(limit)


@app.get("/state/open-blockers", tags=["State"])
async def state_open_blockers():
    return service.open_blockers()


@app.get("/state/agent-health", tags=["State"])
async def state_agent_health():
    return service.agent_health()


@app.get("/state/coined-terms", tags=["State"])
async def state_coined_terms():
    """Each coined term with reference count, last-referenced date, total engagement."""
    return service.coined_terms()


# ---------------------------------------------------------------------------
# Admin (seed + map regeneration)
# ---------------------------------------------------------------------------

@app.post("/admin/seed", tags=["Admin"])
async def admin_seed(force: bool = Query(False)):
    import seed
    return seed.seed_all(service.db_path, force=force)


@app.post("/admin/render-map", tags=["Admin"])
async def admin_render_map(write_html: bool = Query(False), publish: bool = Query(False)):
    return service.render_map(write_json=True, write_html=write_html, publish=publish)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA State Ledger microservice")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
