"""
EVA Activity-Tracker-Agent — data models.

Logs and monitors EVA's day-to-day activity across every lobe, buckets it by
project, catches recurring patterns (blockers, stalled threads, high-activity
zero-revenue zones), and flags revenue traction so time/resources get
reallocated toward whatever is actually moving revenue > 0. Runs once per day
(EOD) and persists a DailyDigest history.

No-circularity rule (mirrors trend-agent / idea-generator-agent): every
pattern/flag is derived from eva-state ledger events actually read that day —
never asserted first and back-filled. Effort is measured as event-count per
project (a proxy, not real time-tracking) — this is stated explicitly in the
digest so nobody mistakes it for logged hours.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

# Same two goal tracks idea-generator-agent's alignment digest uses — kept
# local (not imported cross-module, per this repo's per-module self-
# containment convention) so this agent has zero import-time coupling.
TRACK_REAL_ESTATE = "real_estate"
TRACK_AI_AGENCY = "ai_agency"
GOAL_TRACKS = (TRACK_REAL_ESTATE, TRACK_AI_AGENCY)

# event_type values treated as direct evidence of revenue movement (not
# effort, not intent — actual money-side signal). Extend as new agents wire
# in; unmatched revenue-shaped payload keys are also checked (see engine.py).
REVENUE_EVENT_TYPES = (
    "deal_closed",
    "payment_received",
    "invoice_paid",
    "subscription_started",
    "lead_converted",
    "revenue_milestone",
    "deal_funded",
)

STATUS_OK = "OK"
STATUS_WATCH = "WATCH"
STATUS_DOUBLE_DOWN = "DOUBLE_DOWN"
STATUS_RED_FLAG = "RED_FLAG"


class ActivityBucket(BaseModel):
    """One project/track's activity for the day."""
    project: str
    track: Optional[str] = None
    event_count: int = 0
    event_types: dict[str, int] = Field(default_factory=dict)
    has_revenue_signal: bool = False
    revenue_amount_sum: float = 0.0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class PatternFlag(BaseModel):
    """A detected pattern worth surfacing — recurring blocker, stalled
    thread, or high-effort/zero-revenue drift."""
    kind: str  # "recurring_blocker" | "stalled_thread" | "low_leverage" | "high_leverage"
    project: str
    description: str
    evidence_count: int = 0


class RevenueTractionSignal(BaseModel):
    """A concrete revenue-side event that day — the "double down" trigger."""
    project: str
    event_type: str
    amount: Optional[float] = None
    summary: str = ""
    entity_id: Optional[str] = None


class DailyDigest(BaseModel):
    date: str  # YYYY-MM-DD (day this digest covers)
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_events: int = 0
    buckets: list[ActivityBucket] = Field(default_factory=list)
    patterns: list[PatternFlag] = Field(default_factory=list)
    revenue_signals: list[RevenueTractionSignal] = Field(default_factory=list)
    goal_track_share: float = 0.0  # fraction of today's events in GOAL_TRACKS
    high_leverage_projects: list[str] = Field(default_factory=list)
    low_leverage_projects: list[str] = Field(default_factory=list)
    double_down_recommendation: Optional[str] = None
    course_correction_notes: list[str] = Field(default_factory=list)
    status: str = STATUS_OK

    model_config = {"protected_namespaces": ()}


__all__ = [
    "ActivityBucket", "PatternFlag", "RevenueTractionSignal", "DailyDigest",
    "GOAL_TRACKS", "TRACK_REAL_ESTATE", "TRACK_AI_AGENCY",
    "REVENUE_EVENT_TYPES",
    "STATUS_OK", "STATUS_WATCH", "STATUS_DOUBLE_DOWN", "STATUS_RED_FLAG",
]
