"""
EVA Deal Scout — FastAPI microservice (Module 3)
================================================
Port: 8766

Endpoints:
  POST   /deals                        Create a deal
  GET    /deals                        List all deals (sorted by score desc)
  GET    /deals/shortlist              Deals with overall_score >= 7.5
  GET    /deals/export                 Export all deals as JSON
  GET    /deals/{id}                   Get single deal
  PUT    /deals/{id}                   Update a deal
  DELETE /deals/{id}                   Remove a deal
  POST   /deals/{id}/analyze           Re-run scoring engine on a deal
  POST   /deals/fetch/flippa/{id}      Fetch + persist Flippa listing
  POST   /deals/fetch/ef/{id}          Fetch + persist EF listing
  GET    /health                       Health check
"""

from __future__ import annotations

import argparse
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database as db
from analyzer import analyze_deal
from models import Deal, DealCreate, DealUpdate, HealthResponse
from scrapers.flippa import fetch_flippa_listing
from scrapers.empire_flippers import fetch_ef_listing


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(
    title="EVA Deal Scout",
    description=(
        "Module 3 of the EVA digital acquisition intelligence system. "
        "Tracks and scores digital business acquisition candidates."
    ),
    version="1.0.0",
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
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_deal_from_create(payload: DealCreate) -> Deal:
    """Construct a Deal from a DealCreate payload, apply scoring."""
    ts = _now()
    deal = Deal(
        id=str(uuid.uuid4()),
        source=payload.source,
        listing_id=payload.listing_id,
        url=payload.url,
        name=payload.name,
        category=payload.category,
        monthly_net=payload.monthly_net,
        annual_multiple=payload.annual_multiple,
        asking_price=payload.asking_price,
        age_years=payload.age_years,
        status=payload.status,
        notes=payload.notes,
        # Pass optional score overrides
        ai_proof_score=payload.ai_proof_score or 0.0,
        value_add_score=payload.value_add_score or 0.0,
        created_at=ts,
        updated_at=ts,
    )
    return analyze_deal(deal)


# ---------------------------------------------------------------------------
# Routes — order matters: static paths before parameterised ones
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check():
    """Service liveness check."""
    return HealthResponse(
        status="ok",
        module="eva-deal-scout",
        version="1.0.0",
        db=db.DB_PATH,
    )


# NOTE: /deals/shortlist and /deals/export MUST come before /deals/{id}
# so FastAPI doesn't match the literal strings as UUIDs.

@app.get("/deals/shortlist", tags=["Deals"])
async def get_shortlist():
    """Return deals with overall_score >= 7.5, sorted by score descending."""
    async with db.get_db() as conn:
        rows = await db.fetch_shortlist(conn)
    return {"deals": rows, "count": len(rows)}


@app.get("/deals/export", tags=["Deals"])
async def export_deals():
    """Export all deals as a JSON document."""
    async with db.get_db() as conn:
        rows = await db.fetch_all_deals(conn)
    return JSONResponse(
        content={"deals": rows, "count": len(rows), "exported_at": _now()}
    )


@app.get("/deals", tags=["Deals"])
async def list_deals():
    """List all tracked deals, sorted by overall_score descending."""
    async with db.get_db() as conn:
        rows = await db.fetch_all_deals(conn)
    return {"deals": rows, "count": len(rows)}


@app.post("/deals", status_code=201, tags=["Deals"])
async def create_deal(payload: DealCreate):
    """Manually add a new deal. Scoring is automatically applied."""
    deal = _build_deal_from_create(payload)
    async with db.get_db() as conn:
        await db.insert_deal(conn, deal)
    return deal.model_dump()


@app.get("/deals/{deal_id}", tags=["Deals"])
async def get_deal(deal_id: str = Path(..., description="Deal UUID")):
    """Get a single deal with full analysis fields."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")
    return row


@app.put("/deals/{deal_id}", tags=["Deals"])
async def update_deal(
    payload: DealUpdate,
    deal_id: str = Path(..., description="Deal UUID"),
):
    """Update deal fields. Re-runs scoring engine after applying changes."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        # Merge updates into existing row
        updates = payload.model_dump(exclude_none=True)
        row.update(updates)
        row["updated_at"] = _now()

        deal = Deal(**row)
        scored = analyze_deal(deal)
        await db.update_deal(conn, scored)

    return scored.model_dump()


@app.delete("/deals/{deal_id}", tags=["Deals"])
async def delete_deal(deal_id: str = Path(..., description="Deal UUID")):
    """Remove a deal from the database."""
    async with db.get_db() as conn:
        deleted = await db.delete_deal(conn, deal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")
    return {"deleted": True, "id": deal_id}


@app.post("/deals/{deal_id}/analyze", tags=["Deals"])
async def analyze_deal_endpoint(deal_id: str = Path(..., description="Deal UUID")):
    """Re-run the scoring engine on an existing deal and persist updated scores."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        deal = Deal(**row)
        scored = analyze_deal(deal)
        await db.update_deal(conn, scored)

    return scored.model_dump()


@app.post("/deals/fetch/flippa/{listing_id}", status_code=201, tags=["Fetch"])
async def fetch_flippa(listing_id: str):
    """
    Attempt to fetch basic listing data from a public Flippa page and persist
    as a new deal.  Missing fields are set to safe defaults; re-run
    POST /deals/{id}/analyze after manually filling in monthly_net, etc.
    """
    data = fetch_flippa_listing(listing_id)

    if data.get("error"):
        # Still create a stub so the user can fill in details
        stub_name = data.get("name") or f"Flippa #{listing_id}"
        payload = DealCreate(
            source="flippa",
            listing_id=listing_id,
            url=data["url"],
            name=stub_name,
            category=data.get("category") or "Content",
            monthly_net=data.get("monthly_net") or 0.0,
            annual_multiple=data.get("annual_multiple") or 0.0,
            asking_price=data.get("asking_price") or 0.0,
            age_years=data.get("age_years") or 0.0,
            status="tracking",
            notes=f"[Partial fetch — {data['error']}] {data.get('notes', '')}",
        )
    else:
        payload = DealCreate(
            source="flippa",
            listing_id=listing_id,
            url=data["url"],
            name=data.get("name") or f"Flippa #{listing_id}",
            category=data.get("category") or "Content",
            monthly_net=data.get("monthly_net") or 0.0,
            annual_multiple=data.get("annual_multiple") or 0.0,
            asking_price=data.get("asking_price") or 0.0,
            age_years=data.get("age_years") or 0.0,
            status="tracking",
            notes=data.get("notes") or "",
        )

    deal = _build_deal_from_create(payload)
    async with db.get_db() as conn:
        await db.insert_deal(conn, deal)

    response = deal.model_dump()
    response["fetch_metadata"] = {
        "raw_html_available": data.get("raw_html_available", False),
        "fetch_error": data.get("error"),
        "note": (
            "Some fields may be 0/null — update via PUT /deals/{id} "
            "and re-score via POST /deals/{id}/analyze"
        ),
    }
    return response


@app.post("/deals/fetch/ef/{listing_id}", status_code=201, tags=["Fetch"])
async def fetch_ef(listing_id: str):
    """
    Attempt to fetch basic listing data from a public Empire Flippers page and
    persist as a new deal.  EF multiples are converted from monthly to annual
    (÷ 12) automatically.
    """
    data = fetch_ef_listing(listing_id)

    if data.get("error"):
        stub_name = data.get("name") or f"EF #{listing_id}"
        payload = DealCreate(
            source="empire_flippers",
            listing_id=listing_id,
            url=data["url"],
            name=stub_name,
            category=data.get("category") or "Content",
            monthly_net=data.get("monthly_net") or 0.0,
            annual_multiple=data.get("annual_multiple") or 0.0,
            asking_price=data.get("asking_price") or 0.0,
            age_years=data.get("age_years") or 0.0,
            status="tracking",
            notes=f"[Partial fetch — {data['error']}] {data.get('notes', '')}",
        )
    else:
        payload = DealCreate(
            source="empire_flippers",
            listing_id=listing_id,
            url=data["url"],
            name=data.get("name") or f"EF #{listing_id}",
            category=data.get("category") or "Content",
            monthly_net=data.get("monthly_net") or 0.0,
            annual_multiple=data.get("annual_multiple") or 0.0,
            asking_price=data.get("asking_price") or 0.0,
            age_years=data.get("age_years") or 0.0,
            status="tracking",
            notes=data.get("notes") or "",
        )

    deal = _build_deal_from_create(payload)
    async with db.get_db() as conn:
        await db.insert_deal(conn, deal)

    response = deal.model_dump()
    response["fetch_metadata"] = {
        "raw_html_available": data.get("raw_html_available", False),
        "fetch_error": data.get("error"),
        "note": (
            "Some fields may be 0/null — update via PUT /deals/{id} "
            "and re-score via POST /deals/{id}/analyze. "
            "EF multiple was divided by 12 to normalise to annual."
        ),
    }
    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Deal Scout microservice")
    parser.add_argument(
        "--port",
        type=int,
        default=8766,
        help="Port to bind on (default: 8766)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind on (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable hot reload (dev mode)",
    )
    args = parser.parse_args()

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
