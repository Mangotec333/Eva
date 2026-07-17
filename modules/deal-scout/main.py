"""
EVA Deal Scout — FastAPI microservice (v2)
==========================================
Port: 8766

Endpoints:
  POST   /deals                          Create a deal
  GET    /deals                          List all deals (query: stage, archived, market_status)
  GET    /deals/shortlist                Deals with overall_score >= 7.5
  GET    /deals/export                   Export all deals as JSON
  GET    /deals/pipeline                 Deals grouped by stage (excl. archived)
  GET    /deals/archived                 All archived deals
  GET    /deals/{id}                     Get single deal
  PUT    /deals/{id}                     Update a deal (logs field_update events)
  DELETE /deals/{id}                     Remove a deal
  POST   /deals/{id}/analyze             Re-run scoring engine on a deal
  POST   /deals/{id}/stage               Advance or set stage
  POST   /deals/{id}/archive             Archive a deal
  POST   /deals/{id}/unarchive           Restore a deal from archive
  GET    /deals/{id}/history             Full history log for a deal
  GET    /deals/{id}/competitors        List researched competitors for a deal
  POST   /deals/{id}/competitors        Attach a competitor to a deal
  GET    /deals/{id}/box                 Deal-box hard-criteria verdict (evaluates on demand)
  GET    /box/deals                      List in-box deals (box_pass=True)
  POST   /deals/fetch/flippa/{id}        Fetch + persist Flippa listing
  POST   /deals/fetch/ef/{id}            Fetch + persist EF listing
  GET    /health                         Health check
"""

from __future__ import annotations

import argparse
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import database as db
from analyzer import analyze_deal
from models import (
    Deal, DealCreate, DealUpdate, HealthResponse,
    StageUpdate, ArchiveRequest, VALID_STAGES,
)
from scrapers.flippa import fetch_flippa_listing
from scrapers.empire_flippers import fetch_ef_listing

# Unified DB-backed pipeline (stdlib sqlite3; independent of the legacy
# aiosqlite `deals` table above so existing JSON export compat is preserved).
from store import SQLiteDealStore
from pipeline import source_deals, score_pending
from sources import list_sources
from trends import build_and_save_report, analyze_trends
from backfill import backfill_all

PIPELINE_DB_PATH = "eva-deal-scout.db"


def _pipeline_store() -> SQLiteDealStore:
    store = SQLiteDealStore(PIPELINE_DB_PATH)
    store.migrate()
    return store


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
    version="2.0.0",
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


class CompetitorCreate(BaseModel):
    """Payload for POST /deals/{id}/competitors."""

    name: str
    description: str = ""       # what_they_do
    pricing: str = ""          # pricing_model
    url: str = ""
    source_url: str = ""
    moat_comparison: str = ""
    category: Optional[str] = None


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
        listing_price_original=payload.listing_price_original or payload.asking_price,
        age_years=payload.age_years,
        stage=payload.stage,
        notes=payload.notes,
        buy_vs_build_decision=payload.buy_vs_build_decision,
        buy_vs_build_reason=payload.buy_vs_build_reason,
        market_status=payload.market_status,
        # Pass optional score overrides
        ai_proof_score=payload.ai_proof_score or 0.0,
        value_add_score=payload.value_add_score or 0.0,
        buy_vs_build_score=payload.buy_vs_build_score or 0.0,
        overall_score=payload.overall_score or 0.0,
        discovered_at=ts,
        stage_changed_at=ts if payload.stage != "tracking" else "",
        created_at=ts,
        updated_at=ts,
    )
    return analyze_deal(deal)


# ---------------------------------------------------------------------------
# Routes — order matters: static paths BEFORE parameterised ones
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check():
    """Service liveness check."""
    return HealthResponse(
        status="ok",
        module="eva-deal-scout",
        version="2.0.0",
        db=db.DB_PATH,
    )


# NOTE: /deals/shortlist, /deals/export, /deals/pipeline, /deals/archived
# MUST come before /deals/{id} so FastAPI doesn't match literal strings as UUIDs.

@app.get("/deals/shortlist", tags=["Deals"])
async def get_shortlist():
    """Return non-archived deals with overall_score >= 7.5, sorted by score descending."""
    async with db.get_db() as conn:
        rows = await db.fetch_shortlist(conn)
    return {"deals": rows, "count": len(rows)}


@app.get("/deals/export", tags=["Deals"])
async def export_deals():
    """Export all deals as a JSON document."""
    async with db.get_db() as conn:
        rows = await db.fetch_all_deals(conn, archived="all")
    return JSONResponse(
        content={"deals": rows, "count": len(rows), "exported_at": _now()}
    )


@app.get("/deals/pipeline", tags=["Deals"])
async def get_pipeline():
    """
    Return deals grouped by stage (dict of stage → list of deals).
    Excludes archived deals by default.

    Returns:
        {"tracking": [...], "in_progress": [...], "nda_signed": [...],
         "loi_sent": [...], "due_diligence": [...], "closed": [...]}
    """
    async with db.get_db() as conn:
        pipeline = await db.fetch_pipeline(conn)
    return pipeline


@app.get("/deals/archived", tags=["Deals"])
async def get_archived():
    """Return all archived deals with their archive_reason and archived_at."""
    async with db.get_db() as conn:
        rows = await db.fetch_archived(conn)
    return {"deals": rows, "count": len(rows)}


@app.get("/deals", tags=["Deals"])
async def list_deals(
    stage: Optional[str] = Query(default=None, description="Filter by stage"),
    archived: Optional[str] = Query(default="false", description="'true' | 'false' | 'all'"),
    market_status: Optional[str] = Query(default=None, description="Filter by market_status"),
):
    """List tracked deals, sorted by overall_score descending.

    Query params:
    - stage: filter by pipeline stage
    - archived: 'false' (default, active only), 'true' (archived only), 'all' (everything)
    - market_status: filter by availability
    """
    async with db.get_db() as conn:
        rows = await db.fetch_all_deals(conn, stage=stage, archived=archived, market_status=market_status)
    return {"deals": rows, "count": len(rows)}


@app.post("/deals", status_code=201, tags=["Deals"])
async def create_deal(payload: DealCreate):
    """Manually add a new deal. Scoring is automatically applied. Logs 'created' event."""
    deal = _build_deal_from_create(payload)
    history_event = {
        "deal_id": deal.id,
        "event_type": "created",
        "from_value": "",
        "to_value": deal.stage,
        "field_name": "stage",
        "reason": "Deal created",
        "note": "",
    }
    async with db.get_db() as conn:
        await db.insert_deal_with_history(conn, deal, history_event)
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
async def update_deal_endpoint(
    payload: DealUpdate,
    deal_id: str = Path(..., description="Deal UUID"),
):
    """Update deal fields. Re-runs scoring engine after applying changes.
    Logs a field_update event for every changed field."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        updates = payload.model_dump(exclude_none=True)
        ts = _now()

        # Collect field-level changes before merging
        changed_fields = []
        for field_name, new_val in updates.items():
            old_val = row.get(field_name)
            if str(old_val) != str(new_val):
                changed_fields.append((field_name, str(old_val), str(new_val)))

        row.update(updates)
        row["updated_at"] = ts

        deal = Deal(**row)
        scored = analyze_deal(deal)
        await db.update_deal(conn, scored)

        # Log each changed field
        for field_name, from_val, to_val in changed_fields:
            await db.log_history(conn, {
                "deal_id": deal_id,
                "event_type": "field_update",
                "from_value": from_val,
                "to_value": to_val,
                "field_name": field_name,
                "reason": "",
                "note": "",
            })

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
        await db.log_history(conn, {
            "deal_id": deal_id,
            "event_type": "score_update",
            "from_value": str(deal.overall_score),
            "to_value": str(scored.overall_score),
            "field_name": "overall_score",
            "reason": "Re-scored via /analyze",
            "note": "",
        })

    return scored.model_dump()


@app.post("/deals/{deal_id}/stage", tags=["Deals"])
async def set_stage(
    payload: StageUpdate,
    deal_id: str = Path(..., description="Deal UUID"),
):
    """Advance or set the pipeline stage for a deal.

    Body: {"stage": "nda_signed", "reason": "signed NDA today", "note": ""}
    Validates stage is one of: tracking, in_progress, nda_signed, loi_sent, due_diligence, closed.
    """
    if payload.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage {payload.stage!r}. Must be one of: {VALID_STAGES}",
        )

    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        old_stage = row["stage"]
        ts = _now()
        row["stage"] = payload.stage
        row["stage_changed_at"] = ts
        if payload.stage == "closed":
            row["closed_at"] = ts
        row["updated_at"] = ts

        deal = Deal(**row)
        await db.update_deal_with_history(conn, deal, {
            "deal_id": deal_id,
            "event_type": "stage_change",
            "from_value": old_stage,
            "to_value": payload.stage,
            "field_name": "stage",
            "reason": payload.reason,
            "note": payload.note,
        })

    return deal.model_dump()


@app.post("/deals/{deal_id}/archive", tags=["Deals"])
async def archive_deal(
    payload: ArchiveRequest,
    deal_id: str = Path(..., description="Deal UUID"),
):
    """Archive a deal at any stage.

    Body: {"reason": "price too high", "note": ""}
    Sets is_archived=True, archive_reason, archived_at=now.
    """
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        ts = _now()
        row["is_archived"] = True
        row["archive_reason"] = payload.reason
        row["archived_at"] = ts
        row["updated_at"] = ts

        deal = Deal(**row)
        await db.update_deal_with_history(conn, deal, {
            "deal_id": deal_id,
            "event_type": "archive",
            "from_value": "",
            "to_value": "archived",
            "field_name": "is_archived",
            "reason": payload.reason,
            "note": payload.note,
        })

    return deal.model_dump()


@app.post("/deals/{deal_id}/unarchive", tags=["Deals"])
async def unarchive_deal(deal_id: str = Path(..., description="Deal UUID")):
    """Restore a deal from archive. Resets is_archived=False, archived_at=''."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")

        ts = _now()
        row["is_archived"] = False
        row["archived_at"] = ""
        row["updated_at"] = ts

        deal = Deal(**row)
        await db.update_deal_with_history(conn, deal, {
            "deal_id": deal_id,
            "event_type": "unarchive",
            "from_value": "archived",
            "to_value": "",
            "field_name": "is_archived",
            "reason": "",
            "note": "",
        })

    return deal.model_dump()


@app.get("/deals/{deal_id}/history", tags=["Deals"])
async def get_deal_history(deal_id: str = Path(..., description="Deal UUID")):
    """Return full history log for a deal, sorted by created_at desc."""
    async with db.get_db() as conn:
        row = await db.fetch_deal(conn, deal_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")
        history = await db.fetch_history(conn, deal_id)
    return {"deal_id": deal_id, "history": history, "count": len(history)}


# ---------------------------------------------------------------------------
# Scraper endpoints
# ---------------------------------------------------------------------------

@app.post("/deals/fetch/flippa/{listing_id}", status_code=201, tags=["Fetch"])
async def fetch_flippa(listing_id: str):
    """
    Attempt to fetch basic listing data from a public Flippa page and persist
    as a new deal. Missing fields are set to safe defaults.
    """
    data = fetch_flippa_listing(listing_id)

    if data.get("error"):
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
            stage="tracking",
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
            stage="tracking",
            notes=data.get("notes") or "",
        )

    deal = _build_deal_from_create(payload)
    history_event = {
        "deal_id": deal.id,
        "event_type": "created",
        "from_value": "",
        "to_value": deal.stage,
        "field_name": "stage",
        "reason": "Fetched from Flippa",
        "note": "",
    }
    async with db.get_db() as conn:
        await db.insert_deal_with_history(conn, deal, history_event)

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
    persist as a new deal. EF multiples are converted from monthly to annual (÷ 12).
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
            stage="tracking",
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
            stage="tracking",
            notes=data.get("notes") or "",
        )

    deal = _build_deal_from_create(payload)
    history_event = {
        "deal_id": deal.id,
        "event_type": "created",
        "from_value": "",
        "to_value": deal.stage,
        "field_name": "stage",
        "reason": "Fetched from Empire Flippers",
        "note": "",
    }
    async with db.get_db() as conn:
        await db.insert_deal_with_history(conn, deal, history_event)

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
# Unified pipeline endpoints (DB-backed: source_runs → raw_deals → scored_deals)
# ---------------------------------------------------------------------------

@app.get("/pipeline/sources", tags=["Pipeline"])
async def pipeline_sources():
    """List configured source adapters and SEED sources with trust levels."""
    return list_sources()


@app.post("/pipeline/source/{source}", tags=["Pipeline"])
async def pipeline_source(source: str, payloads: list[dict]):
    """Stage 1 (SOURCE): normalize + persist raw listings from one source."""
    store = _pipeline_store()
    try:
        return source_deals(store, source, payloads)
    except (KeyError, NotImplementedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.close()


@app.post("/pipeline/score", tags=["Pipeline"])
async def pipeline_score():
    """Stage 2 (SCORE): run the gated v6 scorer over pending DB rows."""
    store = _pipeline_store()
    try:
        return score_pending(store)
    finally:
        store.close()


@app.post("/pipeline/backfill", tags=["Pipeline"])
async def pipeline_backfill(
    data_dir: str = Query(default="deal_scout_data"),
    closed_file: str = Query(default="closed_deals_dataset.json"),
):
    """Import existing deal_scout_data/*.json + closed_deals_dataset.json into the DB."""
    store = _pipeline_store()
    try:
        return backfill_all(store, data_dir=data_dir, closed_path=closed_file)
    finally:
        store.close()


@app.get("/pipeline/scored", tags=["Pipeline"])
async def pipeline_scored():
    """Return all scored deals from the pipeline, best first."""
    store = _pipeline_store()
    try:
        rows = [s.model_dump() for s in store.list_scored_deals()]
        return {"deals": rows, "count": len(rows)}
    finally:
        store.close()


@app.get("/pipeline/trends", tags=["Pipeline"])
async def pipeline_trends():
    """Return the computed trend stats over open vs closed comps."""
    store = _pipeline_store()
    try:
        return analyze_trends(store)
    finally:
        store.close()


@app.post("/pipeline/trends/report", tags=["Pipeline"])
async def pipeline_trends_report(
    output: str = Query(default="/home/user/workspace/deal_trend_report_2026-07-16.md"),
):
    """Build + persist a markdown trend report, saving a copy to disk."""
    store = _pipeline_store()
    try:
        report = build_and_save_report(store, output_path=output)
        return {"id": report.id, "generated_at": report.generated_at,
                "output_path": output, "bytes": len(report.report_md)}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Competitor intelligence (DB-backed: raw_deals ← deal_competitors → competitors)
# ---------------------------------------------------------------------------

@app.get("/deals/{deal_id}/competitors", tags=["Competitors"])
async def get_deal_competitors(deal_id: str = Path(..., description="raw_deal id")):
    """List researched competitors linked to a deal (from the pipeline DB)."""
    store = _pipeline_store()
    try:
        comps = [c.model_dump() for c in store.list_competitors(deal_id)]
    finally:
        store.close()
    return {"deal_id": deal_id, "competitors": comps, "count": len(comps)}


@app.post("/deals/{deal_id}/competitors", status_code=201, tags=["Competitors"])
async def add_deal_competitor(
    payload: CompetitorCreate,
    deal_id: str = Path(..., description="raw_deal id"),
):
    """Attach a researched competitor to a deal.  Upserts the shared competitor
    entity (deduped by name) so intel compounds across deals."""
    store = _pipeline_store()
    try:
        comp = store.add_competitor(
            deal_id=deal_id,
            name=payload.name,
            what_they_do=payload.description,
            pricing_model=payload.pricing,
            url=payload.url,
            moat_comparison=payload.moat_comparison,
            source_url=payload.source_url,
            category=payload.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        store.close()
    return comp.model_dump()


# ---------------------------------------------------------------------------
# Deal box (post-scoring hard-criteria verdicts)
# ---------------------------------------------------------------------------

@app.get("/box/deals", tags=["Deal Box"])
async def list_box_deals():
    """List in-box deals (box_pass=True) from the pipeline DB, best cash flow first."""
    store = _pipeline_store()
    try:
        deals = [e.model_dump() for e in store.list_box_deals()]
    finally:
        store.close()
    return {"box_deals": deals, "count": len(deals)}


@app.get("/deals/{deal_id}/box", tags=["Deal Box"])
async def get_deal_box(deal_id: str = Path(..., description="raw_deal id of a scored deal")):
    """Return the deal-box verdict for a scored deal.

    Evaluates on demand (persisting/refreshing the row) so the verdict always
    reflects the current stored metrics and config."""
    store = _pipeline_store()
    try:
        ev = store.evaluate_box(deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        store.close()
    return ev.model_dump()


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
