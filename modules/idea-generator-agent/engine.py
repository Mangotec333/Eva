"""
EVA Idea-Generator-Agent — deterministic scoring engine.

No LLM in the compute path (mirrors trend-agent) — the composite math stays
auditable. Scoring inputs come from evidence supplied by the caller (a human,
an EVA research subagent, or another lobe); the engine only computes.

Formula:
    composite = goal_alignment*w1 + portfolio_synergy*w2 + time_to_results*w3
                + market_demand*w4 + (10 - effort)*w5 + revenue_potential*w6

Default weights (sum to 1.0): goal_alignment 0.20, portfolio_synergy 0.20,
time_to_results 0.20, market_demand 0.15, effort(inverted) 0.10,
revenue_potential 0.15. Speed-to-result was elevated to a top-tier pillar
(co-equal with alignment/synergy) per the 2026-07-20 "optimize for time to
results" decision — a correct idea that takes years to prove itself competes
poorly against one that produces a checkable result in weeks, even at equal
eventual size. Alignment and portfolio fit still carry real weight so this
never overrides the shiny-object guard below.
"""

from __future__ import annotations

from typing import Optional

from models import (
    RECOMMEND_BUILD,
    RECOMMEND_PARTNER,
    RECOMMEND_PASS,
    RECOMMEND_WATCH,
    IdeaInput,
    IdeaScoreResult,
)

DEFAULT_WEIGHTS = {
    "goal_alignment": 0.20,
    "portfolio_synergy": 0.20,
    "time_to_results": 0.20,
    "market_demand": 0.15,
    "effort": 0.10,          # inverted before weighting
    "revenue_potential": 0.15,
}

SLOW_RESULTS_FLOOR = 3.0   # time_to_results_score at/below this on a BUILD call is a flag

BUILD_THRESHOLD = 7.5
WATCH_THRESHOLD = 5.5
SYNERGY_FLOOR_FOR_BUILD = 6.0
LOW_SYNERGY_HIGH_ALIGNMENT_GAP = 3.0   # synergy vs alignment gap that flags "shiny object"
ACQUIRE_EFFORT_FLOOR = 8.0
ACQUIRE_DEMAND_FLOOR = 7.0
UNVERIFIED_DEMAND_SOURCE_MIN = 1


def composite_score(idea: IdeaInput, weights: Optional[dict] = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    score = (
        idea.goal_alignment_score * w["goal_alignment"]
        + idea.portfolio_synergy_score * w["portfolio_synergy"]
        + idea.time_to_results_score * w["time_to_results"]
        + idea.market_demand_score * w["market_demand"]
        + (10 - idea.effort_score) * w["effort"]
        + idea.revenue_potential_score * w["revenue_potential"]
    )
    return round(score, 2)


def recommend(idea: IdeaInput, composite: float) -> str:
    """BUILD / PARTNER / WATCH / PASS — computed from scores, never assumed."""
    if composite >= BUILD_THRESHOLD:
        if idea.portfolio_synergy_score >= SYNERGY_FLOOR_FOR_BUILD:
            return RECOMMEND_BUILD
        # Good idea, but it doesn't leverage what we already own/operate —
        # bring in an operator/partner rather than building from zero.
        return RECOMMEND_PARTNER
    if composite >= WATCH_THRESHOLD:
        return RECOMMEND_WATCH
    return RECOMMEND_PASS


def is_acquire_candidate(idea: IdeaInput) -> bool:
    """Buy-vs-build nod (mirrors deal-scout's buy-vs-build recommendation):
    high demand + very high build effort => check deal-scout for an existing
    operator to acquire instead of building from scratch."""
    return (idea.effort_score >= ACQUIRE_EFFORT_FLOOR
            and idea.market_demand_score >= ACQUIRE_DEMAND_FLOOR)


def compute_flags(idea: IdeaInput, composite: float, recommendation: str) -> list[str]:
    flags: list[str] = []

    if len(idea.demand_sources) < UNVERIFIED_DEMAND_SOURCE_MIN and idea.market_demand_score >= 6:
        flags.append(
            "Unverified demand: market_demand_score >= 6 with no cited "
            "sources — treat this idea as a draft, not a finding.")

    if not idea.counter_notes:
        flags.append(
            "No counter-thesis notes supplied — this idea has not actually "
            "been stress-tested; do not act on it as a clean bill of health.")

    gap = idea.portfolio_synergy_score - idea.goal_alignment_score
    if idea.portfolio_synergy_score >= 7 and idea.goal_alignment_score <= 4:
        flags.append(
            "Shiny-object risk: leverages what we already own/operate but "
            "scores low on goal alignment (Storeys RE / Mangotec AI-agency "
            "revenue) — this is exactly the drift pattern to be the devil's "
            "advocate against.")
    elif abs(gap) >= LOW_SYNERGY_HIGH_ALIGNMENT_GAP:
        flags.append(
            f"Alignment/synergy gap of {gap:+.1f} between portfolio synergy "
            f"({idea.portfolio_synergy_score}) and goal alignment "
            f"({idea.goal_alignment_score}) — reconcile before committing.")

    if recommendation in (RECOMMEND_BUILD, RECOMMEND_PARTNER) and idea.effort_score >= 8:
        flags.append(
            "High effort_score (>=8) on a BUILD/PARTNER call — confirm "
            "capacity exists before committing; this competes directly with "
            "current core (Storeys deals, Eva build) for time.")

    if recommendation == RECOMMEND_BUILD and idea.time_to_results_score <= SLOW_RESULTS_FLOOR:
        flags.append(
            f"Slow time-to-results ({idea.time_to_results_score}<="
            f"{SLOW_RESULTS_FLOOR}) on a BUILD call — this idea won't produce "
            f"a checkable result soon; re-check it still deserves priority "
            f"over faster-payoff work before committing time.")

    return flags


def score_idea(idea: IdeaInput, weights: Optional[dict] = None) -> IdeaScoreResult:
    composite = composite_score(idea, weights)
    recommendation = recommend(idea, composite)
    acquire = is_acquire_candidate(idea)
    flags = compute_flags(idea, composite, recommendation)

    return IdeaScoreResult(
        idea_id=idea.idea_id or idea.title.lower().replace(" ", "_")[:64],
        title=idea.title,
        category=idea.category,
        composite_score=composite,
        recommendation=recommendation,
        acquire_candidate=acquire,
        flags=flags,
        sub_scores={
            "goal_alignment_score": idea.goal_alignment_score,
            "portfolio_synergy_score": idea.portfolio_synergy_score,
            "time_to_results_score": idea.time_to_results_score,
            "market_demand_score": idea.market_demand_score,
            "effort_score": idea.effort_score,
            "revenue_potential_score": idea.revenue_potential_score,
        },
    )


__all__ = [
    "DEFAULT_WEIGHTS",
    "BUILD_THRESHOLD",
    "WATCH_THRESHOLD",
    "composite_score",
    "recommend",
    "is_acquire_candidate",
    "compute_flags",
    "score_idea",
]
