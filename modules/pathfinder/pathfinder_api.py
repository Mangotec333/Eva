"""
EVA Pathfinder — Monetization Funnel Agent
FastAPI microservice on port 8773.

Endpoints:
  POST /pathfinder/lead           — ingest waitlist submission, score, store, return action
  GET  /pathfinder/leads          — list all leads (score, stage, last_contact)
  POST /pathfinder/lead/{id}/advance — advance lead to next pipeline stage
  GET  /health                    — health check
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

# ── Local imports ──────────────────────────────────────────────────────────────
from pathfinder_db import (
    DB_PATH,
    STAGES,
    advance_lead_stage,
    get_all_leads,
    get_follow_up_today,
    get_lead_by_id,
    insert_lead,
    init_db,
)
from outreach_sequences import SEQUENCES, get_first_dm, get_sequence

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="EVA Pathfinder",
    description="Monetization funnel agent — lead scoring, routing, and pipeline management.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://eva.mangotec.ai", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Ensure DB is ready on startup ──────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()
    logger.info(f"Pathfinder DB initialised at {DB_PATH}")


# ── Scoring Constants ──────────────────────────────────────────────────────────
TIER_SCORES: dict[str, tuple[int, str]] = {
    "enterprise": (90, "high-touch"),
    "operator":   (70, "standard"),
    "starter":    (40, "nurture"),
    "unsure":     (50, "discovery"),
}

PAIN_POINT_KEYWORDS = {
    "deal", "acquisition", "pipeline", "search", "acquire", "sourcing",
    "off-market", "off market", "diligence", "target", "seller",
}

PAIN_BONUS = 15


# ── Schemas ───────────────────────────────────────────────────────────────────

class LeadIn(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    tier: str           # enterprise | operator | starter | unsure
    usecase: Optional[str] = None   # free-text pain point / use-case


class LeadOut(BaseModel):
    id: int
    score: int
    sequence: str
    next_action: str
    first_dm: Optional[int] = None
    stage: str


class LeadRecord(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str]
    tier: str
    usecase: Optional[str]
    score: int
    sequence: str
    stage: str
    created_at: str
    last_contact: Optional[str]
    notes: Optional[str]


class LeadsResponse(BaseModel):
    total: int
    follow_up_today: int
    leads: list[LeadRecord]


class AdvanceResponse(BaseModel):
    id: int
    previous_stage: str
    current_stage: str
    last_contact: Optional[str]


# ── Scoring Logic ─────────────────────────────────────────────────────────────

def score_lead(tier: str, usecase: Optional[str]) -> tuple[int, str]:
    """
    Returns (score, sequence) for a given tier + pain point text.

    Tier base scores:
      enterprise → 90, high-touch
      operator   → 70, standard
      starter    → 40, nurture
      unsure     → 50, discovery

    Pain point bonus: +15 if usecase contains acquisition/deal/pipeline/search
    Score is capped at 100.
    """
    tier_key = tier.strip().lower()
    base_score, sequence = TIER_SCORES.get(tier_key, (50, "discovery"))

    bonus = 0
    if usecase:
        usecase_lower = usecase.lower()
        if any(kw in usecase_lower for kw in PAIN_POINT_KEYWORDS):
            bonus = PAIN_BONUS
            logger.info(f"Pain point keyword match — +{PAIN_BONUS} bonus")

    final_score = min(base_score + bonus, 100)
    return final_score, sequence


def build_next_action(sequence: str, score: int) -> str:
    """Return a human-readable next action string based on sequence."""
    seq_def = get_sequence(sequence)
    if not seq_def or not seq_def.get("cadence"):
        return "Review lead manually"

    first_step = seq_def["cadence"][0]
    label = first_step.get("label", "Send first outreach")

    dm_num = first_step.get("dm")
    if dm_num:
        return f"{label} — use DM template #{dm_num}"
    return label


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health_check():
    return {
        "status": "ok",
        "service": "EVA Pathfinder",
        "port": 8773,
        "db": str(DB_PATH),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/pathfinder/lead", response_model=LeadOut, tags=["leads"])
def ingest_lead(lead: LeadIn):
    """
    Ingest a waitlist form submission.
    Scores the lead, selects the outreach sequence, stores in DB,
    and returns the recommended next action.
    """
    score, sequence = score_lead(lead.tier, lead.usecase)

    try:
        lead_id = insert_lead(
            name=lead.name,
            email=lead.email,
            company=lead.company,
            tier=lead.tier,
            usecase=lead.usecase,
            score=score,
            sequence=sequence,
        )
    except Exception as exc:
        # Most likely a UNIQUE constraint violation (duplicate email)
        logger.warning(f"Failed to insert lead {lead.email}: {exc}")
        raise HTTPException(
            status_code=409,
            detail=f"A lead with email '{lead.email}' already exists.",
        )

    next_action = build_next_action(sequence, score)
    first_dm_info = get_first_dm(sequence)
    first_dm_num = first_dm_info["dm_number"] if first_dm_info else None

    logger.info(
        f"New lead #{lead_id}: {lead.name} <{lead.email}> | "
        f"tier={lead.tier} score={score} seq={sequence}"
    )

    return LeadOut(
        id=lead_id,
        score=score,
        sequence=sequence,
        next_action=next_action,
        first_dm=first_dm_num,
        stage="new",
    )


@app.get("/pathfinder/leads", response_model=LeadsResponse, tags=["leads"])
def list_leads():
    """
    Return all leads ordered by score (desc).
    Also surfaces a count of leads that need follow-up today.
    """
    all_leads = get_all_leads()
    follow_ups = get_follow_up_today()

    return LeadsResponse(
        total=len(all_leads),
        follow_up_today=len(follow_ups),
        leads=[LeadRecord(**l) for l in all_leads],
    )


@app.post("/pathfinder/lead/{lead_id}/advance", response_model=AdvanceResponse, tags=["leads"])
def advance_lead(lead_id: int):
    """
    Advance a lead to the next stage in the pipeline.
    Stages: new → contacted → replied → meeting_booked → closed → archived
    """
    existing = get_lead_by_id(lead_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Lead #{lead_id} not found.")

    previous_stage = existing["stage"]

    if previous_stage == STAGES[-1]:
        raise HTTPException(
            status_code=400,
            detail=f"Lead #{lead_id} is already at the final stage: '{previous_stage}'.",
        )

    updated = advance_lead_stage(lead_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to advance lead stage.")

    logger.info(
        f"Lead #{lead_id} advanced: {previous_stage} → {updated['stage']}"
    )

    return AdvanceResponse(
        id=lead_id,
        previous_stage=previous_stage,
        current_stage=updated["stage"],
        last_contact=updated.get("last_contact"),
    )


# ── Dev entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "pathfinder_api:app",
        host="0.0.0.0",
        port=8773,
        reload=True,
        log_level="info",
    )
