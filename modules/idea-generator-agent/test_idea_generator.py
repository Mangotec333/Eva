"""
EVA Idea-Generator-Agent — offline test suite (stubbed eva-state, temp sqlite
store, zero network). Stdlib-only runner (no pytest dependency):

  python modules/idea-generator-agent/test_idea_generator.py
  (or)  cd modules/idea-generator-agent && python test_idea_generator.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force offline + throwaway sqlite BEFORE importing the modules.
os.environ["EVA_IDEA_OFFLINE"] = "1"
_TMP = tempfile.mkdtemp(prefix="idea_generator_test_")
os.environ["EVA_IDEA_DB_PATH"] = os.path.join(_TMP, "idea_generator.db")

from alignment import build_digest  # noqa: E402
from engine import (  # noqa: E402
    compute_flags,
    composite_score,
    is_acquire_candidate,
    is_distraction,
    recommend,
    score_idea,
)
from loop import AlignmentLoop  # noqa: E402
from models import IdeaInput  # noqa: E402
from service import IdeaGeneratorService, slack_alert  # noqa: E402
from state_client import StubStateLedgerClient  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {('- ' + detail) if detail else ''}")


def fresh_service(seed_events=None) -> IdeaGeneratorService:
    return IdeaGeneratorService(state=StubStateLedgerClient(seed_events=seed_events), offline=True)


# -- engine.py --------------------------------------------------------------

def test_composite_score_inverts_effort():
    low_effort = IdeaInput(
        title="A", goal_alignment_score=7, portfolio_synergy_score=7,
        market_demand_score=7, effort_score=1, revenue_potential_score=7,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    high_effort = low_effort.model_copy(update={"effort_score": 9})
    check("lower effort scores higher composite (all else equal)",
          composite_score(low_effort) > composite_score(high_effort))


def test_recommend_build_requires_synergy():
    build_worthy = IdeaInput(
        title="B", goal_alignment_score=9, portfolio_synergy_score=8,
        market_demand_score=9, effort_score=1, revenue_potential_score=8,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    c = composite_score(build_worthy)
    check("high composite + high synergy -> BUILD", recommend(build_worthy, c) == "BUILD",
          f"composite={c}")

    no_synergy = IdeaInput(
        title="B2", goal_alignment_score=10, portfolio_synergy_score=2,
        market_demand_score=10, effort_score=0, revenue_potential_score=10,
        time_to_results_score=10,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    c2 = composite_score(no_synergy)
    check("high composite + low synergy -> PARTNER (not BUILD)",
          recommend(no_synergy, c2) == "PARTNER", f"composite={c2}")


def test_recommend_pass_on_weak_idea():
    weak = IdeaInput(
        title="C", goal_alignment_score=2, portfolio_synergy_score=1,
        market_demand_score=2, effort_score=9, revenue_potential_score=1)
    c = composite_score(weak)
    check("weak idea -> PASS", recommend(weak, c) == "PASS", f"composite={c}")


def test_acquire_candidate_flags_high_demand_high_effort():
    idea = IdeaInput(
        title="D", goal_alignment_score=6, portfolio_synergy_score=5,
        market_demand_score=8, effort_score=9, revenue_potential_score=7)
    check("high demand + high effort -> acquire_candidate", is_acquire_candidate(idea))

    easy = idea.model_copy(update={"effort_score": 2})
    check("low effort -> not acquire_candidate", not is_acquire_candidate(easy))


def test_compute_flags_catches_unverified_demand():
    idea = IdeaInput(
        title="E", goal_alignment_score=6, portfolio_synergy_score=6,
        market_demand_score=8, effort_score=3, revenue_potential_score=6,
        demand_sources=[], counter_notes=["risk"])
    flags = compute_flags(idea, composite_score(idea), recommend(idea, composite_score(idea)))
    check("unverified demand flagged", any("Unverified demand" in f for f in flags), str(flags))


def test_compute_flags_catches_shiny_object_drift():
    idea = IdeaInput(
        title="F", goal_alignment_score=3, portfolio_synergy_score=8,
        market_demand_score=6, effort_score=4, revenue_potential_score=6,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    flags = compute_flags(idea, composite_score(idea), recommend(idea, composite_score(idea)))
    check("shiny-object drift flagged", any("Shiny-object risk" in f for f in flags), str(flags))


def test_compute_flags_catches_mothership_distraction():
    idea = IdeaInput(
        title="H", goal_alignment_score=9, portfolio_synergy_score=9,
        market_demand_score=8, effort_score=8, revenue_potential_score=8,
        mothership_alignment_score=2,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    composite = composite_score(idea)
    result = score_idea(idea)
    flags = compute_flags(idea, composite, recommend(idea, composite))
    check("high effort + low mothership alignment -> distraction_flag",
          result.distraction_flag is True)
    check("distraction reason text present",
          any("Distraction risk" in f for f in flags), str(flags))


def test_low_effort_or_high_mothership_alignment_is_not_distraction():
    low_effort = IdeaInput(
        title="I", goal_alignment_score=9, portfolio_synergy_score=9,
        market_demand_score=8, effort_score=3, revenue_potential_score=8,
        mothership_alignment_score=2)
    check("low effort -> not distraction", not is_distraction(low_effort))

    high_mothership = IdeaInput(
        title="J", goal_alignment_score=9, portfolio_synergy_score=9,
        market_demand_score=8, effort_score=8, revenue_potential_score=8,
        mothership_alignment_score=8)
    check("high mothership alignment -> not distraction",
          not is_distraction(high_mothership))


def test_compute_flags_catches_slow_time_to_results_on_build():
    idea = IdeaInput(
        title="G", goal_alignment_score=10, portfolio_synergy_score=10,
        market_demand_score=10, effort_score=0, revenue_potential_score=10,
        time_to_results_score=1,
        demand_sources=["https://example.com"], counter_notes=["risk"])
    c2 = composite_score(idea)
    rec = recommend(idea, c2)
    flags = compute_flags(idea, c2, rec)
    check("BUILD reached despite slow time-to-results", rec == "BUILD", f"composite={c2}")
    check("slow time-to-results flagged", any("Slow time-to-results" in f for f in flags), str(flags))


def test_compute_flags_catches_missing_counter_thesis():
    idea = IdeaInput(
        title="G", goal_alignment_score=6, portfolio_synergy_score=6,
        market_demand_score=6, effort_score=4, revenue_potential_score=6,
        demand_sources=["https://example.com"], counter_notes=[])
    flags = compute_flags(idea, composite_score(idea), recommend(idea, composite_score(idea)))
    check("missing counter-thesis flagged", any("counter-thesis" in f for f in flags), str(flags))


def test_score_idea_end_to_end():
    idea = IdeaInput(
        title="Fitness coach marketplace", category="fitness",
        goal_alignment_score=2, portfolio_synergy_score=3,
        market_demand_score=6, effort_score=6, revenue_potential_score=5,
        demand_sources=["https://example.com/report"], counter_notes=["saturated market"])
    result = score_idea(idea)
    check("idea_id derived from title", result.idea_id == "fitness_coach_marketplace")
    check("recommendation is one of the four", result.recommendation in
          {"BUILD", "PARTNER", "WATCH", "PASS"})
    check("sub_scores captured", result.sub_scores["market_demand_score"] == 6)


# -- alignment.py -------------------------------------------------------------

def test_build_digest_no_events_is_watch():
    d = build_digest([], window_days=7)
    check("no events -> WATCH status", d.status == "WATCH")
    check("no events -> zero total", d.total_events == 0)


def test_build_digest_off_thesis_triggers_red_flag():
    events = [{"track": "content_marketing"} for _ in range(8)] + \
             [{"track": "real_estate"} for _ in range(2)]
    d = build_digest(events, window_days=7)
    check("off-thesis majority -> RED_FLAG", d.status == "RED_FLAG",
          f"goal_share={d.goal_track_share}")
    check("goal_track_share computed correctly", d.goal_track_share == 0.2)


def test_build_digest_healthy_mix_is_ok():
    events = [{"track": "real_estate"} for _ in range(6)] + \
             [{"track": "ai_agency"} for _ in range(2)] + \
             [{"track": "misc"} for _ in range(2)]
    d = build_digest(events, window_days=7)
    check("healthy goal-track share -> OK", d.status == "OK",
          f"goal_share={d.goal_track_share}")


def test_build_digest_flags_low_synergy_build_pattern():
    low_synergy_event = {
        "track": "real_estate", "event_type": "idea_scored",
        "payload": {"recommendation": "BUILD", "sub_scores": {"portfolio_synergy_score": 2}},
    }
    events = [{"track": "real_estate"} for _ in range(5)] + [low_synergy_event] * 3
    d = build_digest(events, window_days=7)
    check("repeated low-synergy BUILD calls -> RED_FLAG", d.status == "RED_FLAG")
    check("low-synergy build count tallied", d.recent_low_synergy_builds == 3)


# -- service.py ---------------------------------------------------------------

def test_service_score_idea_emits_and_persists():
    svc = fresh_service()
    idea = IdeaInput(
        title="Video analytics for retail foot traffic", category="video_analytics",
        goal_alignment_score=4, portfolio_synergy_score=6,
        market_demand_score=7, effort_score=5, revenue_potential_score=6,
        demand_sources=["https://example.com"], counter_notes=["camera privacy risk"])
    result = svc.score_idea(idea)
    check("scored result returned", result.title == idea.title)
    emitted_types = [e["event_type"] for e in svc.state.events]
    check("idea_scored emitted", "idea_scored" in emitted_types, str(emitted_types))
    runs = svc.list_idea_runs(idea_id=result.idea_id)
    check("idea run persisted", len(runs) == 1, str(runs))


def test_service_alignment_check_offline_safe():
    svc = fresh_service(seed_events=[{"track": "real_estate"}] * 10)
    digest = svc.run_alignment_check(window_days=7)
    check("alignment digest returns OK status shape", digest["status"] in
          {"OK", "WATCH", "RED_FLAG"})
    check("slack_ok key present (None when not red flag)",
          "slack_ok" in digest)
    hist = svc.list_digests(limit=5)
    check("digest persisted to history", len(hist) == 1, str(hist))


def test_slack_alert_no_token_is_honest_failure():
    os.environ.pop("SLACK_BOT_TOKEN", None)
    res = slack_alert("test")
    check("slack_alert never crashes without token", res.get("ok") is False)


def test_loop_offline_safe():
    svc = fresh_service()
    loop = AlignmentLoop(svc, offline=True)
    started = loop.start()
    check("loop does not start when offline", started is False)
    check("loop.is_running() false when offline", loop.is_running() is False)


def test_loop_resilient_to_exceptions():
    class Boom:
        offline = False
        def run_alignment_check(self, **kwargs):
            raise RuntimeError("ledger exploded")

    loop = AlignmentLoop(Boom(), offline=True)
    out = loop.fire()
    check("fire() catches exception", out["ok"] is False and "ledger exploded" in out["error"])
    check("loop survives an exception without crashing",
          len(loop.fires) == 1 and loop.fires[0]["ok"] is False)


def main() -> int:
    for fn in (
        test_composite_score_inverts_effort,
        test_recommend_build_requires_synergy,
        test_recommend_pass_on_weak_idea,
        test_acquire_candidate_flags_high_demand_high_effort,
        test_compute_flags_catches_unverified_demand,
        test_compute_flags_catches_shiny_object_drift,
        test_compute_flags_catches_mothership_distraction,
        test_low_effort_or_high_mothership_alignment_is_not_distraction,
        test_compute_flags_catches_slow_time_to_results_on_build,
        test_compute_flags_catches_missing_counter_thesis,
        test_score_idea_end_to_end,
        test_build_digest_no_events_is_watch,
        test_build_digest_off_thesis_triggers_red_flag,
        test_build_digest_healthy_mix_is_ok,
        test_build_digest_flags_low_synergy_build_pattern,
        test_service_score_idea_emits_and_persists,
        test_service_alignment_check_offline_safe,
        test_slack_alert_no_token_is_honest_failure,
        test_loop_offline_safe,
        test_loop_resilient_to_exceptions,
    ):
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
