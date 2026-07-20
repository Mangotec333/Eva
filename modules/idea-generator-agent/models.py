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

# The mothership WHY sits one level above GOAL_TRACKS. GOAL_TRACKS ($10K/mo
# threshold, Storeys + Mangotec) is the FIRST MILE MARKER on a much longer
# journey — not the destination. The destination is the actual reason any
# of this is being built at all, per explicit 2026-07-20 framing: "Family,
# Lifestyle, IMPACT — inspire and help as many people as possible — all for
# the glory of the Almighty." An idea can score perfectly against the
# current goal and still be a distraction if it burns real energy/time
# without any line of sight to that WHY — that gap is what
# ``mothership_alignment_score`` + ``distraction_flag`` exist to catch.
MOTHERSHIP_WHY = (
    "Family, Lifestyle, Impact — inspire and help as many people as "
    "possible, for the glory of the Almighty"
)


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
    time_to_results_score: float = Field(ge=0, le=10, default=5.0)
    # 10 = fastest to a tangible, checkable result (first lead, first dollar,
    # first live artifact). 0 = long-horizon payoff only. Explicit goal
    # parameter per 2026-07-20 decision: optimize the whole portfolio for
    # speed-to-result, not just eventual size of result.
    mothership_alignment_score: float = Field(ge=0, le=10, default=5.0)
    # 10 = clearly serves the mothership WHY (see MOTHERSHIP_WHY above) —
    # Family, Lifestyle, Impact. 0 = pure grind toward the tactical revenue
    # goal with no line of sight to the actual WHY. This is DELIBERATELY
    # separate from goal_alignment_score: an idea can be perfectly aligned
    # to the $10K/mo mile-marker goal and still score low here if chasing it
    # would cost real energy without ever laddering up to family/lifestyle/
    # impact.

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
    distraction_flag: bool = False
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
