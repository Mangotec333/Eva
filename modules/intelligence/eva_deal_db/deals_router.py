"""
Eva Deal Intelligence — FastAPI Router
Mounts at /deals in Eva's existing FastAPI app.

In your main.py:
    from deals_router import router as deals_router
    app.include_router(deals_router, prefix="/deals", tags=["deals"])
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from deal_repository import DealRepository, Deal
import os

router = APIRouter()
_repo = None

def get_repo() -> DealRepository:
    global _repo
    if _repo is None:
        db_path = os.environ.get("EVA_DEALS_DB", os.path.expanduser("~/Eva/data/eva_deals.db"))
        _repo = DealRepository(db_path=db_path)
    return _repo

# ── GET /deals — list all / filtered ─────────────────────────────────────────
@router.get("/")
def list_deals(
    tier: Optional[int]   = Query(None, description="Filter by tier (1=primary, 2=watch, 3=radar)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    asset_type: Optional[str] = Query(None, description="Filter by asset_type"),
):
    deals = get_repo().list_deals(tier=tier, status=status, asset_type=asset_type)
    return [_deal_summary(d) for d in deals]

# ── GET /deals/stats ──────────────────────────────────────────────────────────
@router.get("/stats")
def stats():
    return get_repo().stats()

# ── GET /deals/{deal_id} — full record ───────────────────────────────────────
@router.get("/{deal_id}")
def get_deal(deal_id: str):
    deal = get_repo().get(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal not found: {deal_id}")
    return _deal_full(deal)

# ── GET /deals/{deal_id}/field/{field} — quick single-field lookup ───────────
@router.get("/{deal_id}/field/{field}")
def get_field(deal_id: str, field: str):
    """
    Eva's fastest query: /deals/batch-ai/field/noi_mo → {"deal_id": "batch-ai", "field": "noi_mo", "value": 1371.0}
    """
    try:
        value = get_repo().get_field(deal_id, field)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if value is None:
        raise HTTPException(status_code=404, detail=f"Deal or field not found")
    return {"deal_id": deal_id, "field": field, "value": value}

# ── GET /deals/search?q=... — keyword search ──────────────────────────────────
@router.get("/search/text")
def search_text(q: str = Query(..., min_length=2), limit: int = 10):
    deals = get_repo().search_text(q, limit=limit)
    return [_deal_summary(d) for d in deals]

# ── GET /deals/{deal_id}/similar — semantic KNN ───────────────────────────────
@router.get("/{deal_id}/similar")
def similar(deal_id: str, k: int = 5):
    results = get_repo().search_similar(deal_id, k=k)
    return results

# ── GET /deals/compare?fields=... ─────────────────────────────────────────────
@router.get("/compare/fields")
def compare(
    fields: str = Query("id,name,tier,noi_mo,multiple,asset_type,status",
                        description="Comma-separated field names"),
    deal_ids: Optional[str] = Query(None, description="Comma-separated deal IDs (optional)")
):
    field_list  = [f.strip() for f in fields.split(",")]
    id_list     = [i.strip() for i in deal_ids.split(",")] if deal_ids else None
    return get_repo().compare(field_list, id_list)

# ── POST /deals — upsert a deal ───────────────────────────────────────────────
@router.post("/")
def upsert_deal(deal: dict):
    try:
        d = Deal(**deal)
        get_repo().upsert(d, embed=False)
        return {"status": "ok", "id": d.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── GET /deals/{deal_id}/events — audit log ───────────────────────────────────
@router.get("/{deal_id}/events")
def get_events(deal_id: str, limit: int = 20):
    return get_repo().get_events(deal_id, limit=limit)

# ── POST /deals/{deal_id}/note — add a note ───────────────────────────────────
@router.post("/{deal_id}/note")
def add_note(deal_id: str, body: dict):
    note = body.get("note", "")
    if not note:
        raise HTTPException(status_code=400, detail="note field required")
    get_repo().log_event(deal_id, "note", note=note)
    return {"status": "ok"}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _deal_summary(d: Deal) -> dict:
    return {
        "id": d.id, "name": d.name, "platform": d.platform,
        "asset_type": d.asset_type, "tier": d.tier, "status": d.status,
        "asking_price": d.asking_price, "multiple": d.multiple,
        "noi_mo": d.noi_mo, "noi_annual": d.noi_annual,
        "mrr": d.mrr, "risk_score": d.risk_score, "eva_score": d.eva_score,
        "last_updated": d.last_updated,
    }

def _deal_full(d: Deal) -> dict:
    return {
        **_deal_summary(d),
        "alias": d.alias, "market": d.market,
        "gross_revenue_mo": d.gross_revenue_mo,
        "operating_exp_mo": d.operating_exp_mo,
        "ebitda_mo": d.ebitda_mo,
        "total_debt_mo": d.total_debt_mo,
        "mrr_peak": d.mrr_peak, "noi_peak_mo": d.noi_peak_mo,
        "cap_rate": d.cap_rate,
        "loan_amount": d.loan_amount, "loan_rate": d.loan_rate,
        "loan_term_yrs": d.loan_term_yrs, "loan_payment_mo": d.loan_payment_mo,
        "risk_flags": d.risk_flags, "eva_notes": d.eva_notes,
        "seller_name": d.seller_name, "seller_email": d.seller_email,
        "loi_date": d.loi_date, "dd_days": d.dd_days,
        "holdback_pct": d.holdback_pct, "holdback_days": d.holdback_days,
        "transition_days": d.transition_days, "transition_hrs_wk": d.transition_hrs_wk,
        "source_url": d.source_url, "extra_fields": d.extra_fields,
    }
