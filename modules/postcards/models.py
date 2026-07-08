"""
EVA Postcards — Pydantic models + domain constants.

Content module that stores Vineet's quote-cards, renders each into a
LinkedIn-style image card (Adam Grant style), queues them on a publish
schedule, and auto-posts to LinkedIn through a wired transport. Publishing is
approval-gated: only ``approved`` cards are released by the scheduler.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Domain constants / enums (kept as plain lists to match repo convention)
# ---------------------------------------------------------------------------

# postcards.status
CARD_STATUS = ["draft", "approved", "posted", "failed"]

# Legal transitions for a card (target -> allowed prior states).
CARD_TRANSITIONS = {
    "approved": {"draft", "failed"},
    "posted": {"approved"},
    "failed": {"approved"},
}

# Schedule defaults (spec section 3/4).
DEFAULT_CADENCE_DAYS = 3
DEFAULT_START_DATE = "2026-07-22"


# ---------------------------------------------------------------------------
# Request payloads (API bodies) — service returns plain dicts
# ---------------------------------------------------------------------------

class CardCreate(BaseModel):
    title: str
    para1: str
    para2: str
    theme: str = ""
    status: str = "draft"
    scheduled_at: str = ""
    actor: str = "system"


class CardUpdate(BaseModel):
    title: Optional[str] = None
    para1: Optional[str] = None
    para2: Optional[str] = None
    theme: Optional[str] = None
    status: Optional[str] = None
    scheduled_at: Optional[str] = None
    actor: str = "system"


class ScheduleUpdate(BaseModel):
    cadence_days: Optional[int] = None
    start_date: Optional[str] = None
    next_due: Optional[str] = None
    actor: str = "system"


class TickRequest(BaseModel):
    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
