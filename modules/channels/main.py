"""
EVA Channels — FastAPI microservice
====================================
Port: 8781  (outreach 8768, postcards 8778, projects 8779,
             linkedin-analytics 8780, channels 8781)

Owns multi-platform publishing transports (v1: Reddit + Substack) behind one
common ``Publisher`` Protocol. Publishing is approval-gated (irreversible), the
change ledger is append-only, and re-publishing is idempotent. No network call
happens here — Reddit/Substack network code lives only in the ``reddit_post.py``
/ ``substack_post.py`` chokepoints.

Endpoints (spec section 5):
  GET    /                       Iconized HTML dashboard (items table)
  GET    /health                 Agent status + last-run summary
  POST   /items                  Create a draft item
  GET    /items                  List items (optional ?status= / ?platform=)
  GET    /items/{id}             Get an item
  PATCH  /items/{id}             Update an item (approve, set payload/scheduled)
  POST   /items/{id}/publish     Publish (gated on status=approved)
  GET    /config/{platform}      Get platform config
  PATCH  /config/{platform}      Update platform config
  GET    /schedule               Get schedule config
  PATCH  /schedule               Update cadence / next_due
  POST   /tick                   Publish next approved-due item, advance next_due
  GET    /ledger                 Query the change ledger
  GET    /ledger/export          Export the ledger (csv|json)
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

import database as db
from models import (
    ConfigUpdate,
    HealthResponse,
    ItemCreate,
    ItemUpdate,
    ScheduleUpdate,
    TickRequest,
)
from service import ChannelsService, ChannelError, NotFoundError
from ui import render_dashboard

VERSION = "1.0.0"

service = ChannelsService()

app = FastAPI(
    title="EVA Channels",
    description=(
        "Multi-platform publishing transports (Reddit + Substack) behind a "
        "common Publisher Protocol, with an approval gate and an append-only "
        "channels ledger."
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
    """Translate domain exceptions into HTTP errors."""
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChannelError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        )


# ---------------------------------------------------------------------------
# Dashboard (iconized, dependency-free HTML)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["View"])
def dashboard():
    return HTMLResponse(content=render_dashboard(service.list_items(), VERSION))


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    st = service.status()
    return HealthResponse(
        status="ok", module="eva-channels", version=VERSION, db=db.DB_PATH,
        providers=st["providers"], last_run=st["last_run"],
        pending_approved=st["pending_approved"], posted_count=st["posted_count"],
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@app.post("/items", status_code=201, tags=["Items"])
def create_item(payload: ItemCreate):
    return _handle(lambda: service.create_item(payload.model_dump()))


@app.get("/items", tags=["Items"])
def list_items(
    status: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
):
    rows = service.list_items(status=status, platform=platform)
    return {"items": rows, "count": len(rows)}


@app.get("/items/{item_id}", tags=["Items"])
def get_item(item_id: str):
    return _handle(lambda: service.get_item(item_id))


@app.patch("/items/{item_id}", tags=["Items"])
def update_item(item_id: str, payload: ItemUpdate):
    fields = payload.model_dump(exclude_none=True)
    actor = fields.pop("actor", "api")
    return _handle(lambda: service.update_item(item_id, fields, actor=actor))


@app.post("/items/{item_id}/publish", tags=["Items"])
def publish_item(item_id: str):
    return _handle(lambda: service.publish_item(item_id, actor="api"))


# ---------------------------------------------------------------------------
# Platform config
# ---------------------------------------------------------------------------

@app.get("/config/{platform}", tags=["Config"])
def get_config(platform: str):
    return _handle(lambda: service.get_config(platform))


@app.patch("/config/{platform}", tags=["Config"])
def update_config(platform: str, payload: ConfigUpdate):
    return _handle(
        lambda: service.update_config(platform, payload.values, actor=payload.actor)
    )


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@app.get("/schedule", tags=["Schedule"])
def get_schedule():
    return service.get_schedule()


@app.patch("/schedule", tags=["Schedule"])
def update_schedule(payload: ScheduleUpdate):
    fields = payload.model_dump(exclude_none=True)
    actor = fields.pop("actor", "api")
    return _handle(lambda: service.update_schedule(fields, actor=actor))


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

@app.post("/tick", tags=["Scheduler"])
def tick(payload: TickRequest = TickRequest()):
    return _handle(lambda: service.tick(actor=payload.actor))


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


@app.get("/ledger/export", tags=["Ledger"])
def export_ledger(format: str = Query(default="json")):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=422, detail="format must be csv or json")
    body = service.export_ledger(format)
    media = "text/csv" if format == "csv" else "application/json"
    return PlainTextResponse(content=body, media_type=media)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Channels microservice")
    parser.add_argument("--port", type=int, default=8781, help="Port (default: 8781)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
