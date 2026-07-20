"""
EVA Idea-Generator-Agent — data models.

Scores new venture/product ideas against the goal (Storeys RE PE fund +
Mangotec AI-agency revenue, per command-center's $10K/mo threshold) and
against the existing portfolio (senior-living RE, Eva/Mangotec AI tooling,
content-engine, GHL, Shopify, etc.) — never in isolation. Also runs a daily
system-wide alignment check (are we spending time/effort on-thesis?).

No-circularity rule (mirrors trend-agent): sub-scores come from evidence
first; the recommendation/verdict is COMPUTED from them, never assumed going
in and back-solved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

RECOMMEND_BUILD = "BUILD"
RECOMMEND_PARTNER = "PARTNER"
RECOMMEND_WATCH = "WATCH"
RECOMMEND_PASS = "PASS"

TRACK_REAL_ESTATE = "real_estate"      # Storeys — senior living / healthcare RE
TRACK_AI_AGENCY = "ai_agency"          # Mangotec — Eva tooling / AI Growth Agency
GOAL_TRACKS = (TRACK_REAL_ESTATE, TRACK_AI_AGENCY)


class IdeaInput(BaseModel):
    """One venture/product idea to score."""

    title: str
    description: str = ""
    category: str = "uncategorized"

    # 0-10 each, sourced from evidence where possible. Higher is always
    # "more of the literal thing" — effort is inverted in the formula, not
    # in the field itself, so the raw number always reads naturally.
    goal_alignment_score: float = Field(ge=0, le=10)
    portfolio_synergy_score: float = Field(ge=0, le=10)
    market_demand_score: float = Field(ge=0, le=10)
    effort_score: float = Field(ge=0, le=10)          # 10 = very high effort/cost
    revenue_potential_score: float = Field(ge=0, le=10)

    synergy_notes: list[str] = Field(default_factory=list)
    demand_sources: list[str] = Field(default_factory=list)
    counter_notes: list[str] = Field(default_factory=list)
    idea_id: Optional[str] = None


class IdeaScoreResult(BaseModel):
    idea_id: str
    title: str
    category: str
    composite_score: float
    recommendation: str
    acquire_candidate: bool = False
    flags: list[str] = Field(default_factory=list)
    sub_scores: dict = Field(default_factory=dict)
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AlignmentDigest(BaseModel):
    """Daily system-wide drift check across all EVA activity/eva-state events."""

    window_days: int
    total_events: int
    goal_track_share: float           # 0-1, fraction of events in GOAL_TRACKS
    off_thesis_share: float
    recent_low_synergy_builds: int    # BUILD recs in window with synergy < threshold
    red_flags: list[str] = Field(default_factory=list)
    status: str = "OK"                # OK | WATCH | RED_FLAG
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
