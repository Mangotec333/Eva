"""
EVA Retro-Agent — data models.

The weekly retrospective agent: every Monday it reviews the prior 7 days and
answers, deterministically, whether the week moved the $10K/month critical path
or just churned infrastructure. It buckets the week into four lenses —

  (a) what SHIPPED (new/updated modules, catalog changes, GitHub commits),
  (b) revenue-pipeline MOVEMENT (did a Product/Revenue Pipeline row actually
      change stage — e.g. Pending→Live, a deal closed — vs. internal churn),
  (c) STALE blockers (anything Pending / Needs-review / awaiting-reply for
      more than 7 days without movement),
  (d) whether last week's stated COURSE-CORRECTION priorities were worked on
      (read from the Weekly Retrospective Log).

— and rolls them up into a goal-drift status ladder (mirrors
activity-tracker-agent's DOUBLE_DOWN/RED_FLAG/WATCH/OK idea, goal-drift flavored):

  REVENUE_WIN > STALLED_BLOCKER > DRIFTING > ON_TRACK.

No-circularity rule (mirrors activity-tracker-agent / trend-agent): every flag is
derived from eva-state events / catalog diffs / retro-log entries actually read
that week — never asserted first and back-filled. Effort/shipping is measured as
event-count from the ledger (a proxy, not real time-tracking), stated explicitly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

# --- goal-drift status ladder ------------------------------------------------
STATUS_ON_TRACK = "ON_TRACK"
STATUS_DRIFTING = "DRIFTING"              # infra work, no revenue movement
STATUS_STALLED_BLOCKER = "STALLED_BLOCKER"  # something pending > 7 days
STATUS_REVENUE_WIN = "REVENUE_WIN"        # a pipeline row actually advanced

# Precedence high→low. A revenue win is the headline (mirrors activity-tracker's
# DOUBLE_DOWN override); a >7-day stall outranks generic drift.
STATUS_PRECEDENCE = (
    STATUS_REVENUE_WIN,
    STATUS_STALLED_BLOCKER,
    STATUS_DRIFTING,
    STATUS_ON_TRACK,
)

# --- event-type vocabularies (read from eva-state) ---------------------------
# "what shipped" — internal build/churn signal (NOT revenue).
SHIPPED_EVENT_TYPES = (
    "module_shipped",
    "module_created",
    "module_updated",
    "catalog_updated",
    "github_commit",
    "commit_pushed",
    "deploy_applied",
    "deploy_landing_applied",
    "pr_opened",
    "pr_merged",
)

# A real revenue-side event (same core set activity-tracker-agent uses, kept
# local per the repo's per-module self-containment convention).
REVENUE_EVENT_TYPES = (
    "deal_closed",
    "payment_received",
    "invoice_paid",
    "subscription_started",
    "lead_converted",
    "revenue_milestone",
    "deal_funded",
)

# Pipeline stage-advance detector: a to_stage containing any of these (case-
# insensitive) is a genuine revenue-pipeline win, not just internal movement.
REVENUE_WIN_STAGES = ("live", "closed", "won", "paid", "funded", "signed", "converted")

# Events / statuses that mark something as an OPEN blocker (awaiting action).
BLOCKER_EVENT_TYPES = (
    "blocker_opened",
    "awaiting_reply",
    "needs_review",
    "pending_review",
    "task_stalled",
    "loi_sent",
    "revenue_leak_found",
)
# Events that RESOLVE a blocker — their presence (as the latest event for an
# entity) means it is no longer stuck.
RESOLVED_EVENT_TYPES = (
    "blocker_resolved",
    "reply_received",
    "review_approved",
    "pipeline_stage_changed",
    "deal_closed",
    "payment_received",
)
# payload.status strings that mean "still pending".
BLOCKER_STATUSES = (
    "pending",
    "pending-high",
    "needs-review",
    "needs_review",
    "awaiting-reply",
    "awaiting_reply",
    "blocked",
    "open",
)

STALE_AFTER_DAYS = 7  # Vineet's doctrine: pending > 7 days without movement.

# payload keys checked (in order) for a numeric revenue amount.
REVENUE_PAYLOAD_KEYS = ("revenue_amount", "amount", "deal_amount", "mrr_delta", "payment_amount")


class ShippedItem(BaseModel):
    """One build/churn artifact shipped in the window (infra signal)."""
    kind: str  # "module" | "catalog" | "commit" | "deploy" | ...
    name: str
    event_type: str
    summary: str = ""
    timestamp: Optional[str] = None


class PipelineMovement(BaseModel):
    """A Product/Revenue Pipeline row that moved this week."""
    pipeline: str
    from_stage: Optional[str] = None
    to_stage: Optional[str] = None
    is_revenue_win: bool = False
    amount: Optional[float] = None
    summary: str = ""
    timestamp: Optional[str] = None


class StaleBlocker(BaseModel):
    """An item pending / needs-review / awaiting-reply > 7 days without
    movement — derived from the last event that touched it."""
    name: str
    status: str
    last_movement: Optional[str] = None
    age_days: int = 0
    summary: str = ""


class PriorityCheck(BaseModel):
    """Whether one of last week's stated course-correction priorities actually
    got worked on this week. ``addressed`` is DERIVED from this week's events —
    never asserted (no-circularity)."""
    priority: str
    addressed: bool = False
    evidence: str = ""


class RetroDigest(BaseModel):
    week_start: str  # YYYY-MM-DD (inclusive)
    week_end: str    # YYYY-MM-DD (the Monday the retro runs, exclusive-ish)
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = STATUS_ON_TRACK
    revenue_win: bool = False

    shipped: list[ShippedItem] = Field(default_factory=list)
    pipeline_movements: list[PipelineMovement] = Field(default_factory=list)
    stale_blockers: list[StaleBlocker] = Field(default_factory=list)
    priority_checks: list[PriorityCheck] = Field(default_factory=list)

    prior_priorities_source: str = ""      # where last week's priorities came from
    shipped_count: int = 0
    revenue_movement_count: int = 0
    priorities_addressed: int = 0
    priorities_total: int = 0

    drift_note: Optional[str] = None
    course_correction_notes: list[str] = Field(default_factory=list)
    narrative: str = ""                    # human-readable digest (brain may sharpen)

    model_config = {"protected_namespaces": ()}


__all__ = [
    "STATUS_ON_TRACK", "STATUS_DRIFTING", "STATUS_STALLED_BLOCKER",
    "STATUS_REVENUE_WIN", "STATUS_PRECEDENCE",
    "SHIPPED_EVENT_TYPES", "REVENUE_EVENT_TYPES", "REVENUE_WIN_STAGES",
    "BLOCKER_EVENT_TYPES", "RESOLVED_EVENT_TYPES", "BLOCKER_STATUSES",
    "STALE_AFTER_DAYS", "REVENUE_PAYLOAD_KEYS",
    "ShippedItem", "PipelineMovement", "StaleBlocker", "PriorityCheck",
    "RetroDigest",
]
