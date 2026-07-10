"""
EVA Postcards — FastAPI microservice
=====================================
Port: 8778  (deal-scout 8766, deal-analyzer 8767, outreach 8768)

Stores Vineet's quote-cards, renders each to a LinkedIn-style PNG (Adam Grant
style), queues them on a publish schedule, and auto-posts to LinkedIn through a
pluggable publisher. Approval-gated: only ``approved`` cards are released by the
scheduler. No network call is made in v1 — publishing goes through the
``StubPublisher``; the LinkedIn transport lives behind ``linkedin_post.py``.

Endpoints (spec section 5):
  POST   /cards                 Create a card (auto-rendered)
  GET    /cards                 List cards (optional ?status=)
  GET    /cards/{id}            Get a card
  PATCH  /cards/{id}            Update a card (approve, set scheduled_at, ...)
  POST   /cards/{id}/render     Render the PNG
  GET    /cards/{id}/image      Serve the PNG
  POST   /cards/seed            Load the 8 authored quotes (idempotent)
  GET    /schedule              Get schedule config
  PATCH  /schedule              Update cadence_days / start_date
  POST   /tick                  Scheduler step (post next due, advance next_due)
  GET    /ledger                Query publish ledger
  GET    /ledger/export         Export ledger (csv|json)
  GET    /health                Health check
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import database as db
from models import (
    CardCreate,
    CardUpdate,
    HealthResponse,
    ScheduleUpdate,
    TickRequest,
)
from service import NotFoundError, PostcardError, PostcardsService

VERSION = "1.0.0"

service = PostcardsService()

app = FastAPI(
    title="EVA Postcards",
    description=(
        "Quote-card content store + Adam Grant-style renderer + approval-gated "
        "LinkedIn publish scheduler with an append-only publish ledger."
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
    except PostcardError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    return HealthResponse(status="ok", module="eva-postcards", version=VERSION, db=db.DB_PATH)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@app.post("/cards", status_code=201, tags=["Cards"])
def create_card(payload: CardCreate):
    return _handle(lambda: service.create_card(payload.model_dump()))


@app.get("/cards", tags=["Cards"])
def list_cards(status: Optional[str] = Query(default=None)):
    rows = service.list_cards(status=status)
    return {"cards": rows, "count": len(rows)}


# NOTE: the /cards/seed route is declared before /cards/{card_id} so the literal
# path takes precedence over the path parameter.
@app.post("/cards/seed", tags=["Cards"])
def seed_cards():
    return _handle(lambda: service.seed(actor="api"))


@app.get("/cards/{card_id}", tags=["Cards"])
def get_card(card_id: str):
    return _handle(lambda: service.get_card(card_id))


@app.patch("/cards/{card_id}", tags=["Cards"])
def update_card(card_id: str, payload: CardUpdate):
    fields = payload.model_dump(exclude_none=True)
    actor = fields.pop("actor", "api")
    return _handle(lambda: service.update_card(card_id, fields, actor=actor))


@app.post("/cards/{card_id}/render", tags=["Cards"])
def render_card_endpoint(card_id: str):
    return _handle(lambda: service.render(card_id, actor="api"))


@app.get("/cards/{card_id}/image", tags=["Cards"])
def get_card_image(card_id: str):
    card = _handle(lambda: service.get_card(card_id))
    path = card.get("image_path", "")
    if not path or not os.path.exists(path):
        path = service.render(card_id, actor="api")["image_path"]
    return FileResponse(path, media_type="image/png", filename=f"{card_id}.png")


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
# Publish ledger
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
    parser = argparse.ArgumentParser(description="EVA Postcards microservice")
    parser.add_argument("--port", type=int, default=8778, help="Port (default: 8778)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
