"""Unit tests for trend_engine.py — deterministic scoring math."""

from __future__ import annotations

from models import SectorAssessment, ThesisRunInput
from trend_engine import durability_score, rank_sectors, run_thesis_model, thesis_verdict


def test_durability_score_inverts_ai_exposure():
    # High AI exposure should pull the score down even with strong resilience/demand.
    high_exposure = durability_score(historical_resilience=9, ai_disruption_exposure=9, structural_demand=9)
    low_exposure = durability_score(historical_resilience=9, ai_disruption_exposure=1, structural_demand=9)
    assert low_exposure > high_exposure


def test_durability_score_weights_sum_to_full_range():
    # Perfect resilience/demand + zero AI exposure => max score of 10.
    assert durability_score(10, 0, 10) == 10.0
    # Zero resilience/demand + full AI exposure => min score of 0.
    assert durability_score(0, 10, 0) == 0.0


def test_rank_sectors_orders_descending_and_assigns_rank():
    sectors = [
        SectorAssessment(name="A", historical_resilience_score=5, ai_disruption_exposure_score=5, structural_demand_score=5),
        SectorAssessment(name="B", historical_resilience_score=9, ai_disruption_exposure_score=1, structural_demand_score=9),
        SectorAssessment(name="C", historical_resilience_score=2, ai_disruption_exposure_score=8, structural_demand_score=2),
    ]
    ranked = rank_sectors(sectors, weights=(0.35, 0.35, 0.30))
    assert [s.name for s in ranked] == ["B", "A", "C"]
    assert [s.rank for s in ranked] == [1, 2, 3]


def test_thesis_verdict_supported_when_all_sectors_strong():
    verdict, confidence = thesis_verdict(avg_score=8.0, min_score=7.0, pass_threshold=6.5)
    assert verdict == "SUPPORTED"
    assert confidence == "HIGH"


def test_thesis_verdict_partially_supported_with_weak_laggard():
    verdict, confidence = thesis_verdict(avg_score=7.0, min_score=3.0, pass_threshold=6.5)
    assert verdict == "PARTIALLY_SUPPORTED"


def test_thesis_verdict_refuted_when_avg_far_below_threshold():
    verdict, confidence = thesis_verdict(avg_score=3.0, min_score=1.0, pass_threshold=6.5)
    assert verdict == "REFUTED"


def test_run_thesis_model_end_to_end_flags_high_ai_exposure():
    inp = ThesisRunInput(
        thesis_statement="Test thesis",
        sectors=[
            SectorAssessment(
                name="Education",
                historical_resilience_score=7,
                ai_disruption_exposure_score=7.5,
                structural_demand_score=6,
                sources=["https://example.com/source"],
            ),
        ],
    )
    result = run_thesis_model(inp)
    assert result.scored_sectors[0].name == "Education"
    assert any("high AI disruption exposure" in f for f in result.flags)
    assert result.verdict in {"SUPPORTED", "PARTIALLY_SUPPORTED", "REFUTED"}
