"""
EVA Signal Intelligence — FastAPI Router
Endpoints: save, get, list, search, validate, close, supersede, stats, due-for-validation, opinion-ledger
Version 1.0 | June 2026
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from .signal_repository import SignalRepository

router = APIRouter(prefix="/signals", tags=["Signal Intelligence"])
repo   = SignalRepository()


# ─────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────

class SaveSignalRequest(BaseModel):
    signal_type:    str
    source:         str
    title:          str
    body:           str
    source_detail:  Optional[str] = None
    raw_source_text: Optional[str] = None
    domain:         Optional[List[str]] = []
    applies_to:     Optional[List[str]] = []
    confidence:     float = Field(default=0.7, ge=0.0, le=1.0)
    stance:         str = "belief"
    is_actionable:  bool = False
    valid_until:    Optional[str] = None
    brief_date:     Optional[str] = None
    brief_snippet:  Optional[str] = None
    validation_days: int = 30


class ValidateSignalRequest(BaseModel):
    verdict:         str   # 'still_true' | 'partially_true' | 'false' | 'outdated' | 'needs_more_data'
    evidence:        Optional[str] = None
    new_confidence:  Optional[float] = None
    validator:       str = "eva"


class CloseSignalRequest(BaseModel):
    reason:         str   # 'outcome_proved' | 'outcome_disproved' | 'new_evidence' | 'time_expired' | 'manual'
    outcome_note:   Optional[str] = None
    final_status:   str = "invalidated"


class SupersedeSignalRequest(BaseModel):
    new_title:       str
    new_body:        str
    new_confidence:  float = 0.7
    new_stance:      str = "belief"
    reason:          str = "new_evidence"
    outcome_note:    Optional[str] = None


class BriefBatchRequest(BaseModel):
    brief_date: str
    signals: List[SaveSignalRequest]


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/", summary="Save a new signal")
def save_signal(req: SaveSignalRequest):
    signal_id = repo.save(**req.dict())
    return {"id": signal_id, "status": "saved"}


@router.get("/stats", summary="DB health stats")
def get_stats():
    return repo.stats()


@router.get("/active", summary="List active signals")
def list_active(
    signal_type: Optional[str] = Query(None),
    applies_to:  Optional[str] = Query(None),
    limit:       int = Query(50, le=200),
):
    return repo.active(signal_type=signal_type, applies_to=applies_to, limit=limit)


@router.get("/due", summary="Signals due for monthly validation")
def list_due():
    return repo.due_for_validation()


@router.get("/opinion-ledger", summary="Full opinion change history")
def opinion_ledger():
    return repo.opinion_ledger()


@router.get("/search", summary="Full-text search signals")
def search_signals(
    q:     str = Query(..., description="Search query"),
    limit: int = Query(20, le=100),
):
    return repo.search(q, limit=limit)


@router.get("/recent", summary="Signals from last N days of briefs")
def recent(days: int = Query(7, le=90)):
    return repo.recent_briefs(days=days)


@router.get("/{signal_id}", summary="Get a single signal by ID")
def get_signal(signal_id: str):
    sig = repo.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig


@router.post("/{signal_id}/validate", summary="Record a validation review")
def validate_signal(signal_id: str, req: ValidateSignalRequest):
    try:
        action = repo.validate(signal_id, **req.dict())
        return {"id": signal_id, "action_taken": action}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{signal_id}/close", summary="Close a signal permanently")
def close_signal(signal_id: str, req: CloseSignalRequest):
    try:
        repo.close(signal_id, **req.dict())
        return {"id": signal_id, "status": "closed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{signal_id}/supersede", summary="Supersede (version) a signal with a new belief")
def supersede_signal(signal_id: str, req: SupersedeSignalRequest):
    try:
        new_id = repo.supersede(signal_id, **req.dict())
        return {"old_id": signal_id, "new_id": new_id, "status": "versioned"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/batch/brief", summary="Batch-save signals from a morning brief")
def save_brief_batch(req: BriefBatchRequest):
    signals = [s.dict() for s in req.signals]
    ids = repo.save_brief_signals(brief_date=req.brief_date, signals=signals)
    return {"brief_date": req.brief_date, "saved": len(ids), "ids": ids}
