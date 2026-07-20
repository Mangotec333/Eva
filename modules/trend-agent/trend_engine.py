"""
EVA Trend Agent — deterministic scoring engine
=================================================

Turns qualitative research inputs (SectorAssessment: historical resilience,
AI disruption exposure, structural demand — each sourced from evidence) into
a ranked, weighted durability scorecard and a thesis verdict.

No-Circularity Rule: the engine never assumes a verdict and back-fills scores
to match it. Sub-scores come from research (see cases/*.json `sources`); the
durability score and verdict are ALWAYS derived from those sub-scores here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from models import SectorAssessment, SectorScore, ThesisRunInput, ThesisRunResult

ENGINE_VERSION = "1.0.0"


def durability_score(
    historical_resilience: float,
    ai_disruption_exposure: float,
    structural_demand: float,
    weights: tuple[float, float, float] = (0.35, 0.35, 0.30),
) -> float:
    """0-10 composite. AI disruption exposure is inverted (10 - exposure)
    before weighting, since higher exposure = lower durability."""
    w_hist, w_ai, w_demand = weights
    inverted_ai = 10.0 - ai_disruption_exposure
    score = (
        historical_resilience * w_hist
        + inverted_ai * w_ai
        + structural_demand * w_demand
    )
    return round(score, 2)


def rank_sectors(sectors: list[SectorAssessment], weights: tuple[float, float, float]) -> list[SectorScore]:
    scored = []
    for s in sectors:
        d = durability_score(
            s.historical_resilience_score,
            s.ai_disruption_exposure_score,
            s.structural_demand_score,
            weights,
        )
        scored.append(
            SectorScore(
                name=s.name,
                historical_resilience_score=s.historical_resilience_score,
                ai_disruption_exposure_score=s.ai_disruption_exposure_score,
                structural_demand_score=s.structural_demand_score,
                durability_score=d,
            )
        )
    scored.sort(key=lambda x: x.durability_score, reverse=True)
    for i, s in enumerate(scored, start=1):
        s.rank = i
    return scored


def thesis_verdict(avg_score: float, min_score: float, pass_threshold: float) -> tuple[str, str]:
    """Verdict is derived purely from the computed scores, never asserted upfront.

    SUPPORTED: avg >= threshold AND no sector far below it (weakest link matters —
               a thesis claiming ALL 5 sectors are durable fails if one is not).
    PARTIALLY_SUPPORTED: avg >= threshold but at least one sector lags meaningfully,
               OR avg is within 1.0 of threshold.
    REFUTED: avg < threshold - 1.0.
    """
    if avg_score >= pass_threshold and min_score >= pass_threshold - 1.5:
        return "SUPPORTED", "HIGH"
    if avg_score >= pass_threshold:
        return "PARTIALLY_SUPPORTED", "MEDIUM"
    if avg_score >= pass_threshold - 1.0:
        return "PARTIALLY_SUPPORTED", "LOW"
    return "REFUTED", "MEDIUM"


def run_thesis_model(inp: ThesisRunInput) -> ThesisRunResult:
    scored = rank_sectors(inp.sectors, inp.weights)
    scores = [s.durability_score for s in scored]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    min_score = min(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0

    verdict, confidence = thesis_verdict(avg_score, min_score, inp.verdict_pass_threshold)

    flags: list[str] = []
    for s in scored:
        if s.ai_disruption_exposure_score >= 6.5:
            flags.append(f"{s.name}: high AI disruption exposure ({s.ai_disruption_exposure_score}/10) — re-underwrite sub-vertical mix")
        if s.structural_demand_score <= 4.0:
            flags.append(f"{s.name}: weak structural demand score ({s.structural_demand_score}/10) — verify thesis fit before allocating")
    if max_score - min_score >= 4.0:
        flags.append("Wide dispersion between strongest and weakest sector — thesis is sector-dependent, not uniformly true")

    return ThesisRunResult(
        thesis_statement=inp.thesis_statement,
        horizon_years=inp.horizon_years,
        scored_sectors=scored,
        avg_durability_score=avg_score,
        min_durability_score=min_score,
        max_durability_score=max_score,
        verdict=verdict,
        verdict_confidence=confidence,
        macro_context=inp.macro_context,
        counter_thesis_points=inp.counter_thesis_points,
        flags=flags,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
