"""
EVA Activity-Tracker-Agent — offline test suite (stubbed eva-state, temp
sqlite store, zero network). Stdlib-only runner (no pytest dependency):

  python modules/activity-tracker-agent/test_activity_engine.py
  (or)  cd modules/activity-tracker-agent && python test_activity_engine.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force offline + throwaway sqlite BEFORE importing the modules.
os.environ["EVA_ACTIVITY_OFFLINE"] = "1"
_TMP = tempfile.mkdtemp(prefix="activity_tracker_test_")
os.environ["EVA_ACTIVITY_DB_PATH"] = os.path.join(_TMP, "activity_tracker.db")

from engine import build_digest  # noqa: E402
from loop import DailyDigestLoop  # noqa: E402
from models import (  # noqa: E402
    STATUS_DOUBLE_DOWN,
    STATUS_OK,
    STATUS_RED_FLAG,
    STATUS_WATCH,
)
from service import ActivityTrackerService, slack_alert  # noqa: E402
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


def fresh_service(seed_events=None) -> ActivityTrackerService:
    return ActivityTrackerService(state=StubStateLedgerClient(seed_events=seed_events), offline=True)


DATE = "2026-07-22"


def ev(project, event_type, track="real_estate", **payload):
    return {
        "project": project, "event_type": event_type, "track": track,
        "timestamp": f"{DATE}T10:00:00+00:00", "payload": payload,
    }


# -- engine.py ----------------------------------------------------------------

def test_build_digest_no_events_is_red_flag():
    d = build_digest([], date=DATE)
    check("no events -> RED_FLAG (logging gap)", d.status == STATUS_RED_FLAG)
    check("no events -> zero total", d.total_events == 0)
    check("gap note present", any("logged today" in n for n in d.course_correction_notes))


def test_build_digest_revenue_event_triggers_double_down():
    events = [ev("Storeys Fund", "deal_closed", revenue_amount=50000)] + \
             [ev("Storeys Fund", "task_progress") for _ in range(3)]
    d = build_digest(events, date=DATE)
    check("revenue event -> DOUBLE_DOWN", d.status == STATUS_DOUBLE_DOWN)
    check("revenue signal captured", len(d.revenue_signals) == 1, str(d.revenue_signals))
    check("high leverage project listed", "Storeys Fund" in d.high_leverage_projects)
    check("double_down_recommendation set", d.double_down_recommendation is not None)


def test_build_digest_payload_amount_counts_as_revenue():
    events = [ev("EVA", "custom_win", amount=1200)]
    d = build_digest(events, date=DATE)
    check("payload amount -> revenue signal", len(d.revenue_signals) == 1, str(d.revenue_signals))
    check("amount captured", d.revenue_signals[0].amount == 1200.0)


def test_build_digest_off_thesis_is_red_flag():
    events = [ev("Random Project", "task_progress", track="misc") for _ in range(9)] + \
             [ev("Storeys Fund", "task_progress", track="real_estate")]
    d = build_digest(events, date=DATE)
    check("off-thesis majority -> RED_FLAG", d.status == STATUS_RED_FLAG,
          f"goal_share={d.goal_track_share}")
    check("goal_track_share computed correctly", d.goal_track_share == 0.1)


def test_build_digest_recurring_blocker_pattern():
    events = [ev("EVA Worker", "task_stalled") for _ in range(2)] + \
             [ev("EVA Worker", "task_progress") for _ in range(4)]
    d = build_digest(events, date=DATE)
    kinds = [p.kind for p in d.patterns]
    check("recurring_blocker flagged", "recurring_blocker" in kinds, str(kinds))


def test_build_digest_low_leverage_pattern_is_watch():
    events = [ev("Griffin Dashboard", "task_progress", track="misc") for _ in range(6)] + \
             [ev("Storeys Fund", "task_progress", track="real_estate") for _ in range(6)]
    d = build_digest(events, date=DATE)
    check("high-activity/no-revenue -> WATCH", d.status == STATUS_WATCH, f"status={d.status}")
    check("low leverage project listed", "Griffin Dashboard" in d.low_leverage_projects)


def test_build_digest_healthy_day_is_ok():
    events = [ev("Storeys Fund", "task_progress", track="real_estate") for _ in range(3)] + \
             [ev("EVA Worker", "task_progress", track="ai_agency") for _ in range(2)]
    d = build_digest(events, date=DATE)
    check("normal day with no triggers -> OK", d.status == STATUS_OK, f"status={d.status}")


# -- service.py -----------------------------------------------------------------

def test_service_run_daily_digest_emits_and_persists():
    seed = [ev("Storeys Fund", "deal_closed", revenue_amount=75000)]
    svc = fresh_service(seed_events=seed)
    result = svc.run_daily_digest(date=DATE)
    check("digest date matches", result["date"] == DATE)
    check("status is DOUBLE_DOWN", result["status"] == STATUS_DOUBLE_DOWN)
    emitted_types = [e["event_type"] for e in svc.state.events]
    check("activity_digest_ready emitted", "activity_digest_ready" in emitted_types, str(emitted_types))
    check("revenue_traction_detected emitted", "revenue_traction_detected" in emitted_types, str(emitted_types))
    persisted = svc.get_digest(DATE)
    check("digest persisted to sqlite", persisted is not None and persisted["date"] == DATE)


def test_service_red_flag_day_emits_alert_event():
    svc = fresh_service(seed_events=[])
    result = svc.run_daily_digest(date=DATE)
    check("empty day -> RED_FLAG", result["status"] == STATUS_RED_FLAG)
    emitted_types = [e["event_type"] for e in svc.state.events]
    check("activity_red_flag emitted", "activity_red_flag" in emitted_types, str(emitted_types))


def test_slack_alert_no_token_is_honest_failure():
    os.environ.pop("SLACK_BOT_TOKEN", None)
    res = slack_alert("test")
    check("slack_alert never crashes without token", res.get("ok") is False)


def test_loop_offline_safe():
    svc = fresh_service()
    loop = DailyDigestLoop(svc, offline=True)
    started = loop.start()
    check("loop does not start when offline", started is False)
    check("loop.is_running() false when offline", loop.is_running() is False)


def test_loop_resilient_to_exceptions():
    class Boom:
        offline = False
        def run_daily_digest(self, **kwargs):
            raise RuntimeError("ledger exploded")

    loop = DailyDigestLoop(Boom(), offline=True)
    out = loop.fire()
    check("fire() catches exception", out["ok"] is False and "ledger exploded" in out["error"])
    check("loop survives an exception without crashing",
          len(loop.fires) == 1 and loop.fires[0]["ok"] is False)


def main() -> int:
    for fn in (
        test_build_digest_no_events_is_red_flag,
        test_build_digest_revenue_event_triggers_double_down,
        test_build_digest_payload_amount_counts_as_revenue,
        test_build_digest_off_thesis_is_red_flag,
        test_build_digest_recurring_blocker_pattern,
        test_build_digest_low_leverage_pattern_is_watch,
        test_build_digest_healthy_day_is_ok,
        test_service_run_daily_digest_emits_and_persists,
        test_service_red_flag_day_emits_alert_event,
        test_slack_alert_no_token_is_honest_failure,
        test_loop_offline_safe,
        test_loop_resilient_to_exceptions,
    ):
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
