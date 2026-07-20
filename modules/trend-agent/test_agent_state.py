"""Integration tests: TrendAgent.run_thesis() emits to eva-state via the
StubStateLedgerClient. Mirrors idea-generator-agent's service-level emit
tests — offline, no network, asserts on the recorded event shape."""

from __future__ import annotations

from agent import TrendAgent
from models import SectorAssessment, ThesisRunInput
from state_client import StubStateLedgerClient

STRONG_SECTOR = SectorAssessment(
    name="Healthcare", historical_resilience_score=9,
    ai_disruption_exposure_score=1, structural_demand_score=9,
    sources=["https://example.com/source"],
)
WEAK_SECTOR = SectorAssessment(
    name="Ad-tech", historical_resilience_score=2,
    ai_disruption_exposure_score=9, structural_demand_score=2,
    sources=["https://example.com/source"],
)


def test_every_run_emits_thesis_run_completed():
    client = StubStateLedgerClient()
    agent = TrendAgent(state_client=client)
    agent.run_thesis(ThesisRunInput(
        thesis_statement="Basic needs endure", sectors=[STRONG_SECTOR]))
    kinds = [e["event_type"] for e in client.events]
    assert "thesis_run_completed" in kinds


def test_supported_verdict_does_not_emit_thesis_refuted():
    client = StubStateLedgerClient()
    agent = TrendAgent(state_client=client)
    result = agent.run_thesis(ThesisRunInput(
        thesis_statement="Basic needs endure", sectors=[STRONG_SECTOR]))
    assert result.verdict == "SUPPORTED"
    assert "thesis_refuted" not in [e["event_type"] for e in client.events]


def test_refuted_verdict_emits_urgent_thesis_refuted():
    client = StubStateLedgerClient()
    agent = TrendAgent(state_client=client)
    result = agent.run_thesis(ThesisRunInput(
        thesis_statement="Ad-tech is the future", sectors=[WEAK_SECTOR]))
    assert result.verdict == "REFUTED"
    refuted = [e for e in client.events if e["event_type"] == "thesis_refuted"]
    assert len(refuted) == 1
    assert refuted[0]["payload"]["urgent"] is True
    assert refuted[0]["payload"]["verdict"] == "REFUTED"


def main() -> int:
    tests = [
        test_every_run_emits_thesis_run_completed,
        test_supported_verdict_does_not_emit_thesis_refuted,
        test_refuted_verdict_emits_urgent_thesis_refuted,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
