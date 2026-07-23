"""
EVA Retro-Agent — offline test suite (stubbed eva-state + retro-log, temp
sqlite ledger, zero network). Stdlib-only runner (no pytest dependency):

  python modules/retro-agent/test_retro_agent.py
  (or)  cd modules/retro-agent && python test_retro_agent.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force offline + throwaway sqlite BEFORE importing the modules.
os.environ["EVA_RETRO_OFFLINE"] = "1"
_TMP = tempfile.mkdtemp(prefix="retro_agent_test_")
os.environ["EVA_RETRO_DB_PATH"] = os.path.join(_TMP, "retro_agent.db")

import memory  # noqa: E402
from brain import StubRetroBrain, make_brain  # noqa: E402
from engine import build_retro  # noqa: E402
from models import (  # noqa: E402
    STATUS_DRIFTING,
    STATUS_ON_TRACK,
    STATUS_REVENUE_WIN,
    STATUS_STALLED_BLOCKER,
)
from retro_log import StubRetroLogSource, parse_log_markdown  # noqa: E402
from service import RetroService  # noqa: E402
from state_client import StubStateLedgerClient  # noqa: E402

WEEK_START = "2026-07-16"
WEEK_END = "2026-07-23"

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


def ev(event_type, *, ts=f"{WEEK_END}T10:00:00+00:00", entity_id="", summary="", **payload):
    return {
        "event_type": event_type,
        "entity_id": entity_id,
        "summary": summary,
        "timestamp": ts,
        "payload": payload,
    }


# -- engine.py ----------------------------------------------------------------

def test_no_events_is_drift_gap():
    d = build_retro([], week_start=WEEK_START, week_end=WEEK_END)
    check("no events -> DRIFTING (verification gap)", d.status == STATUS_DRIFTING, d.status)
    check("no events -> zero shipped", d.shipped_count == 0)
    check("gap note present",
          any("logging gap" in n.lower() or "cannot verify" in n.lower()
              for n in d.course_correction_notes))


def test_revenue_pipeline_stage_change_is_win():
    events = [ev("pipeline_stage_changed", entity_id="Eva Morning Brief",
                 pipeline="Eva Morning Brief", from_stage="Pending", to_stage="Live")]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END)
    check("stage->Live -> REVENUE_WIN", d.status == STATUS_REVENUE_WIN, d.status)
    check("revenue_win flag set", d.revenue_win is True)
    check("one revenue movement", d.revenue_movement_count == 1, str(d.revenue_movement_count))


def test_revenue_event_counts_as_win():
    events = [ev("deal_closed", entity_id="batch.ai", revenue_amount=250000)]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END)
    check("deal_closed -> REVENUE_WIN", d.status == STATUS_REVENUE_WIN, d.status)
    check("amount captured on movement",
          any(m.amount == 250000.0 for m in d.pipeline_movements))


def test_shipped_no_revenue_is_drift():
    events = [ev("module_shipped", entity_id=f"module-{i}", name=f"module-{i}")
              for i in range(4)]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END)
    check("infra shipped, no revenue -> DRIFTING", d.status == STATUS_DRIFTING, d.status)
    check("shipped counted", d.shipped_count == 4, str(d.shipped_count))
    check("drift_note set", bool(d.drift_note))


def test_stale_blocker_outranks_drift():
    # LOI sent 7+ weeks before week_end, no reply since -> stale blocker.
    events = [
        ev("loi_sent", ts="2026-06-01T09:00:00+00:00", entity_id="batch.ai LOI",
           summary="LOI sent to seller"),
        ev("module_shipped", entity_id="some-module", name="some-module"),
    ]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END)
    check("stale blocker present", len(d.stale_blockers) == 1, str(d.stale_blockers))
    check("stale outranks drift -> STALLED_BLOCKER", d.status == STATUS_STALLED_BLOCKER, d.status)
    check("blocker age > 7 days", d.stale_blockers[0].age_days > 7,
          str(d.stale_blockers[0].age_days))


def test_resolved_blocker_is_not_stale():
    events = [
        ev("loi_sent", ts="2026-06-01T09:00:00+00:00", entity_id="batch.ai LOI"),
        ev("reply_received", ts="2026-06-05T09:00:00+00:00", entity_id="batch.ai LOI"),
    ]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END)
    check("resolved blocker dropped", len(d.stale_blockers) == 0, str(d.stale_blockers))


def test_priorities_addressed_derived_from_evidence():
    events = [ev("module_shipped", entity_id="Eva Morning Brief GHL pipeline",
                 name="Eva Morning Brief GHL pipeline")]
    priors = ["Ship the GHL pipeline for Eva Morning Brief",
              "Close the batch.ai LOI (seller reply)"]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END,
                    prior_priorities=priors, prior_priorities_source="stub")
    check("2 priorities tracked", d.priorities_total == 2, str(d.priorities_total))
    check("only the worked-on priority is addressed", d.priorities_addressed == 1,
          str(d.priorities_addressed))
    addressed = [c.priority for c in d.priority_checks if c.addressed]
    check("morning-brief priority addressed",
          any("Morning Brief" in p for p in addressed), str(addressed))


def test_healthy_week_is_on_track():
    # A touched prior priority, no stale blockers, no infra-only drift, but also
    # something shipped that matches the priority (so not a pure gap).
    events = [ev("module_shipped", entity_id="ghl onboarding", name="ghl onboarding"),
              ev("pipeline_stage_changed", entity_id="Eva Morning Brief",
                 to_stage="Live", pipeline="Eva Morning Brief")]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END,
                    prior_priorities=["ghl onboarding SOP"])
    # revenue win present -> REVENUE_WIN (headline), confirms ladder precedence.
    check("shipped + revenue win -> REVENUE_WIN", d.status == STATUS_REVENUE_WIN, d.status)


def test_on_track_when_priority_touched_no_drift():
    events = [ev("pipeline_stage_changed", entity_id="X", to_stage="Discovery",
                 pipeline="X")]  # non-win stage change, so not revenue win, not infra-only
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END,
                    prior_priorities=[])
    check("non-win movement, no shipped, no stale -> ON_TRACK",
          d.status == STATUS_ON_TRACK, d.status)


# -- retro_log.py --------------------------------------------------------------

def test_parse_log_markdown_picks_newest():
    text = (
        "## 2026-07-09\n"
        "Course-correction priorities:\n"
        "- Old priority one\n\n"
        "## 2026-07-16\n"
        "Course-correction priorities:\n"
        "- Close the batch.ai LOI (seller reply)\n"
        "- Ship the GHL pipeline for Eva Morning Brief\n"
    )
    entry = parse_log_markdown(text)
    check("picks newest dated entry", entry.date == "2026-07-16", entry.date or "")
    check("parses both bullets", len(entry.priorities) == 2, str(entry.priorities))
    check("no old-entry bleed", all("Old priority" not in p for p in entry.priorities))


def test_parse_log_markdown_empty():
    entry = parse_log_markdown("no dates here")
    check("empty log -> not ok", entry.ok is False)


# -- brain.py ------------------------------------------------------------------

def test_stub_brain_never_changes_narrative():
    brain = make_brain(offline=True)
    check("offline make_brain -> Stub", isinstance(brain, StubRetroBrain))
    out = brain.sharpen({"narrative": "ORIGINAL", "status": "DRIFTING"})
    check("stub keeps narrative verbatim", out["narrative"] == "ORIGINAL")
    check("stub tokens=0", out["tokens"] == 0)


# -- service.py ----------------------------------------------------------------

def _fresh_service(seed_events=None, priorities=None):
    return RetroService(
        state=StubStateLedgerClient(seed_events=seed_events or []),
        log_source=StubRetroLogSource(priorities=priorities or [], date=WEEK_START),
        brain=StubRetroBrain(),
        offline=True,
    )


def test_service_run_persists_and_emits():
    seed = [ev("pipeline_stage_changed", entity_id="Eva Morning Brief",
               to_stage="Live", pipeline="Eva Morning Brief")]
    svc = _fresh_service(seed_events=seed)
    result = svc.run_retro(week_end=WEEK_END)
    check("window end matches", result["week_end"] == WEEK_END, result.get("week_end", ""))
    check("status REVENUE_WIN", result["status"] == STATUS_REVENUE_WIN, result["status"])
    check("run_id returned", bool(result.get("run_id")))
    emitted = [e["event_type"] for e in svc.state.events]
    check("retro_digest_ready emitted", "retro_digest_ready" in emitted, str(emitted))
    check("retro_revenue_win emitted", "retro_revenue_win" in emitted, str(emitted))
    latest = svc.latest()
    check("digest persisted + hydrated", latest is not None and latest["status"] == STATUS_REVENUE_WIN)


def test_service_stalled_blocker_emits_signal():
    seed = [ev("loi_sent", ts="2026-06-01T09:00:00+00:00", entity_id="batch.ai LOI")]
    svc = _fresh_service(seed_events=seed)
    result = svc.run_retro(week_end=WEEK_END)
    check("status STALLED_BLOCKER", result["status"] == STATUS_STALLED_BLOCKER, result["status"])
    emitted = [e["event_type"] for e in svc.state.events]
    check("retro_stalled_blocker emitted", "retro_stalled_blocker" in emitted, str(emitted))


def test_service_no_events_reports_gap_not_clean():
    svc = _fresh_service(seed_events=[])
    result = svc.run_retro(week_end=WEEK_END)
    check("empty week -> DRIFTING (gap)", result["status"] == STATUS_DRIFTING, result["status"])
    emitted = [e["event_type"] for e in svc.state.events]
    check("retro_drift_flagged emitted", "retro_drift_flagged" in emitted, str(emitted))


# -- memory.py -----------------------------------------------------------------

def test_ledger_is_append_only():
    run_id = memory.save_digest({"week_start": WEEK_START, "week_end": WEEK_END,
                                 "status": STATUS_ON_TRACK})
    check("save returns run id", bool(run_id))
    got = memory.get_digest(run_id)
    check("get_digest round-trips", got is not None and got["id"] == run_id)

    conn = sqlite3.connect(os.environ["EVA_RETRO_DB_PATH"])
    try:
        raised_update = False
        try:
            conn.execute("UPDATE retro_runs SET status='HACKED' WHERE id=?", (run_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            raised_update = True
        except sqlite3.OperationalError:
            raised_update = True
        check("UPDATE blocked by immutability trigger", raised_update)

        raised_delete = False
        try:
            conn.execute("DELETE FROM retro_runs WHERE id=?", (run_id,))
            conn.commit()
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            raised_delete = True
        check("DELETE blocked by immutability trigger", raised_delete)
    finally:
        conn.close()


# -- July 23 2026 seed scenario (the manual retro this agent automates) --------

def test_july_23_seed_scenario():
    """Reproduce the 2026-07-23 manual retro: batch.ai LOI stalled 7+ weeks,
    30+ modules shipped, Eva Morning Brief the only 'live' row but its GHL
    pipeline still pending, realized revenue ~$0. Expect STALLED_BLOCKER
    (stale outranks drift) + a drift note + only some priorities addressed."""
    events = [ev("loi_sent", ts="2026-06-01T09:00:00+00:00", entity_id="batch.ai LOI",
                 summary="LOI to seller, awaiting reply")]
    events += [ev("module_shipped", entity_id=f"module-{i}", name=f"module-{i}")
               for i in range(30)]
    # symbolic $100 seed investment — NOT customer revenue, no pipeline stage move.
    events += [ev("note_logged", entity_id="seed", summary="$100 symbolic seed investment")]
    priors = [
        "Close the batch.ai LOI (seller reply)",
        "Ship the GHL pipeline for Eva Morning Brief",
        "Land the first paying Morning Brief customer",
    ]
    d = build_retro(events, week_start=WEEK_START, week_end=WEEK_END,
                    prior_priorities=priors, prior_priorities_source="local")
    check("seed: STALLED_BLOCKER headline", d.status == STATUS_STALLED_BLOCKER, d.status)
    check("seed: no revenue win", d.revenue_win is False)
    check("seed: batch.ai LOI is the stale blocker",
          any("batch.ai" in b.name.lower() for b in d.stale_blockers), str(d.stale_blockers))
    check("seed: 30 modules shipped", d.shipped_count == 30, str(d.shipped_count))
    check("seed: infra-outpacing-revenue drift noted", bool(d.drift_note))
    check("seed: not all priorities addressed", d.priorities_addressed < d.priorities_total,
          f"{d.priorities_addressed}/{d.priorities_total}")


def main() -> int:
    for fn in (
        test_no_events_is_drift_gap,
        test_revenue_pipeline_stage_change_is_win,
        test_revenue_event_counts_as_win,
        test_shipped_no_revenue_is_drift,
        test_stale_blocker_outranks_drift,
        test_resolved_blocker_is_not_stale,
        test_priorities_addressed_derived_from_evidence,
        test_healthy_week_is_on_track,
        test_on_track_when_priority_touched_no_drift,
        test_parse_log_markdown_picks_newest,
        test_parse_log_markdown_empty,
        test_stub_brain_never_changes_narrative,
        test_service_run_persists_and_emits,
        test_service_stalled_blocker_emits_signal,
        test_service_no_events_reports_gap_not_clean,
        test_ledger_is_append_only,
        test_july_23_seed_scenario,
    ):
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
