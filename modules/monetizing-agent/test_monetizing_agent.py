"""
EVA Monetizing Agent — offline test suite (Stub transports, zero network).

Covers: the scoring model, ledger immutability (the trigger), Sunday-brief
generation, the approval gate (and that execution refuses unapproved plays), and
the shared KB index writer's Stub transport.

Run:  python -m pytest modules/monetizing-agent/
"""

from __future__ import annotations

import os
import sqlite3

import pytest

import memory
import playbook
from brain import StubMonetizationBrain
from mining import StubSignalSource
from scan import render_brief, run_scan
from service import MonetizingService, StubExecutionTransport

# Force the offline stub brain/source everywhere.
os.environ["EVA_MONETIZE_OFFLINE"] = "1"


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "memory.db")
    memory.init_db(path)
    return path


# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

def test_weights_sum_to_one():
    assert round(sum(playbook.WEIGHTS.values()), 6) == 1.0


def test_composite_in_range_and_weighted():
    dims = {"cash_proximity": 100, "effort": 100, "strategic_fit": 100,
            "reusability": 100, "urgency": 100}
    assert playbook.composite_score(dims) == 100.0
    zero = {k: 0 for k in playbook.WEIGHTS}
    assert playbook.composite_score(zero) == 0.0


def test_cash_proximity_dominates_ranking():
    """A ready-to-pay lead should outrank a cold, low-engagement one."""
    hot = playbook.score_signal({
        "kind": "lead", "subject": "hot", "stage": "negotiation", "engagement": 8,
    })
    cold = playbook.score_signal({
        "kind": "lead", "subject": "cold", "engagement": 0, "age_days": 1,
    })
    assert hot["score"] > cold["score"]


def test_match_play_rules():
    assert playbook.match_play({"kind": "lost_deal"}) == "Revive"
    assert playbook.match_play({"kind": "waitlist", "engagement": 0}) == "Outreach"
    assert playbook.match_play({"kind": "spec"}) == "Productize"
    assert playbook.match_play({"kind": "workflow"}) == "White-label"
    assert playbook.match_play({"kind": "content", "has_cta": False}) == "Content-to-offer"
    assert playbook.match_play({"kind": "lead"}) == "Reactivate"
    # explicit suggestion wins when valid
    assert playbook.match_play({"suggested_play": "Referral"}) == "Referral"


# ---------------------------------------------------------------------------
# Ledger immutability (the trigger)
# ---------------------------------------------------------------------------

def test_ledger_blocks_identity_update(db):
    pid = memory.record_play(
        brief_id="b1", play_type="Reactivate", source_signal="lead",
        score=50.0, cash_estimate=1000.0, action_artifact={"kind": "sms"}, path=db,
    )
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE monetization_plays SET score = 99 WHERE play_id = ?", (pid,))
            conn.commit()
    finally:
        conn.close()


def test_ledger_blocks_delete(db):
    pid = memory.record_play(
        brief_id="b1", play_type="Upsell", source_signal="x",
        score=10.0, cash_estimate=0.0, action_artifact={}, path=db,
    )
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM monetization_plays WHERE play_id = ?", (pid,))
            conn.commit()
    finally:
        conn.close()


def test_ledger_allows_lifecycle_update(db):
    """Only status/executed_at/outcome may change — approve + execute must work."""
    pid = memory.record_play(
        brief_id="b1", play_type="Outreach", source_signal="x",
        score=10.0, cash_estimate=0.0, action_artifact={}, path=db,
    )
    memory.approve_plays("b1", path=db)
    memory.mark_executed(pid, outcome="executed", path=db)
    row = memory.list_plays(brief_id="b1", path=db)[0]
    assert row["status"] == memory.STATUS_EXECUTED
    assert row["executed_at"] is not None
    assert row["outcome"] == "executed"


# ---------------------------------------------------------------------------
# Scan + brief generation
# ---------------------------------------------------------------------------

def test_scan_produces_pending_brief(db):
    result = run_scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                      db_path=db, write_report=False, offline=True)
    assert result["status"] == memory.STATUS_PENDING
    assert 1 <= len(result["plays"]) <= 5
    # ranked descending by score
    scores = [p["score"] for p in result["plays"]]
    assert scores == sorted(scores, reverse=True)
    # every play has a concrete artifact
    assert all(p["action_artifact"] for p in result["plays"])


def test_brief_format(db):
    result = run_scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                      db_path=db, write_report=False, offline=True)
    text = result["brief_text"]
    assert text.startswith("EVA SUNDAY MONETIZATION")
    assert 'Reply "go" to execute all' in text
    # one numbered line per play
    for i in range(1, len(result["plays"]) + 1):
        assert f"{i}. [" in text


def test_render_brief_includes_feedback():
    plays = [{"play_type": "Reactivate", "source_signal": "lead", "score": 60.0,
              "cash_estimate": 4000.0, "action_artifact": {"kind": "sms"}}]
    text = render_brief(plays, "Last week: 2 of 5 converted ($3k).",
                        week_of="2026-07-13", est_cash=4000.0)
    assert "Last week: 2 of 5 converted" in text


def test_scan_writes_kb_index_via_stub(db):
    from kb_index import StubIndexTransport
    transport = StubIndexTransport()
    result = run_scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                      db_path=db, write_report=True, index_transport=transport,
                      offline=True)
    assert result["index_result"]["ok"] is True
    assert result["index_result"]["stub"] is True
    assert len(transport.rows) == 1
    assert os.path.exists(result["report_path"])


# ---------------------------------------------------------------------------
# Approval gate + gated execution
# ---------------------------------------------------------------------------

def test_approval_gate_and_execution(db):
    svc = MonetizingService(db_path=db, execution_transport=StubExecutionTransport(),
                            offline=True)
    scan = svc.scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                    write_report=False)
    brief_id = scan["brief_id"]

    # Execution BEFORE approval must not touch any play.
    pre = svc.execute(brief_id)
    assert pre["executed"] == 0
    assert all(r.get("skipped") for r in pre["results"])

    # Approve -> plays flip to approved.
    approved = svc.approve(brief_id)
    assert approved["approved_plays"] == len(scan["plays"])
    assert approved["status"] == memory.STATUS_APPROVED

    # Now execution runs through the Stub transport.
    post = svc.execute(brief_id)
    assert post["executed"] == len(scan["plays"])
    brief = svc.get_brief(brief_id)
    assert brief["status"] == memory.STATUS_EXECUTED


def test_latest_brief_roundtrip(db):
    svc = MonetizingService(db_path=db, offline=True)
    svc.scan(source=StubSignalSource(), brain=StubMonetizationBrain(), write_report=False)
    latest = svc.latest_brief()
    assert latest is not None
    assert latest["plays"]


# ---------------------------------------------------------------------------
# Follow-up feedback loop
# ---------------------------------------------------------------------------

def test_feedback_block_appears_after_outcomes(db):
    svc = MonetizingService(db_path=db, offline=True)
    first = svc.scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                     write_report=False)
    pid = first["plays"][0]["play_id"]
    svc.record_outcome(pid, first["plays"][0]["play_type"], "converted",
                       lesson="SMS > email for reactivation")
    second = svc.scan(source=StubSignalSource(), brain=StubMonetizationBrain(),
                      write_report=False)
    assert "Last week:" in second["brief_text"]
