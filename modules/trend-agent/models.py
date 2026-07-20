"""
EVA Trend Agent — Pydantic models
===================================

Macro-thesis stress-testing model. Tests whether a strategic thesis (e.g.
"society always converges to basic-needs industries regardless of AI/crypto/
currency disruption") holds up against evidence, and scores candidate
sectors on durability so EVA can rank where to allocate capital, product,
or acquisition attention over a multi-year horizon.

Every derived score is COMPUTED from the three input sub-scores via
trend_engine.py — never hardcoded. See directive.md "Scoring Rule".
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SectorAssessment(BaseModel):
    """One candidate sector's durability inputs. Scores are 0-10, sourced from
    research evidence (see `sources`), not guessed."""

    name: str = Field(..., description="e.g. 'Healthcare', 'Shelter', 'Food'")
    historical_resilience_score: float = Field(
        ..., ge=0, le=10,
        description="How stable was demand/revenue/employment through past shocks (2008 GFC, COVID, dot-com)?"
    )
    ai_disruption_exposure_score: float = Field(
        ..., ge=0, le=10,
        description="How exposed is this sector to AI-driven commoditization/margin compression? Higher = MORE exposed/risky."
    )
    structural_demand_score: float = Field(
        ..., ge=0, le=10,
        description="Strength of structural demand drivers over the horizon (demographics, scarcity, regulation, climate)."
    )
    resilient_sub_verticals: list[str] = Field(default_factory=list)
    exposed_sub_verticals: list[str] = Field(default_factory=list)
    counter_thesis_notes: list[str] = Field(
        default_factory=list, description="Evidence/arguments AGAINST this sector being durable"
    )
    sources: list[str] = Field(default_factory=list, description="URLs the scores are grounded in")


class SectorScore(BaseModel):
    name: str
    historical_resilience_score: float
    ai_disruption_exposure_score: float
    structural_demand_score: float
    durability_score: float = Field(..., description="Weighted composite, 0-10, COMPUTED by trend_engine.py")
    rank: int = 0


class ThesisRunInput(BaseModel):
    thesis_statement: str
    horizon_years: int = 10
    sectors: list[SectorAssessment]
    macro_context: str = Field("", description="Narrative synthesis of the 10-yr macro outlook")
    counter_thesis_points: list[str] = Field(default_factory=list)
    weights: tuple[float, float, float] = Field(
        (0.35, 0.35, 0.30),
        description="(historical_resilience, 1 - ai_disruption_exposure, structural_demand) weights, must sum to 1.0"
    )
    verdict_pass_threshold: float = Field(6.5, description="Avg durability score at/above which thesis is judged SUPPORTED")
    source_notes: str = ""


class ThesisRunResult(BaseModel):
    thesis_statement: str
    horizon_years: int
    scored_sectors: list[SectorScore]
    avg_durability_score: float
    min_durability_score: float
    max_durability_score: float
    verdict: str = Field(..., description="SUPPORTED | PARTIALLY_SUPPORTED | REFUTED")
    verdict_confidence: str = Field(..., description="LOW | MEDIUM | HIGH")
    macro_context: str
    counter_thesis_points: list[str]
    recommendations: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    computed_at: str = ""


class AgentHealth(BaseModel):
    status: str
    module: str
    version: str
    directive_version: str
