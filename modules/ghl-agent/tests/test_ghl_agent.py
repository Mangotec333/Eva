"""
EVA GHL Agent — offline test suite (stub GHL + stub state ledger, zero network).

Covers: the 7-touch voice DNA, ledger immutability (the trigger), the funnel
build idempotency (create-then-skip + manual_required fallback), the lead-capture
loop, webhook -> lead-lifecycle mapping, and state-ledger event emission.

Run:  python -m pytest modules/ghl-agent/
"""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ["EVA_GHL_OFFLINE"] = "1"

import campaign
import memory
from ghl_client import StubGHLClient
from service import ACQUISITION_TAG, GHLAgentService
from state_client import StubStateLedgerClient


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "ghl_agent.db")
    memory.init_db(path)
    return path


@pytest.fixture()
def svc(db):
    return GHLAgentService(db_path=db, ghl=StubGHLClient(),
                           state=StubStateLedgerClient(), offline=True)


# ---------------------------------------------------------------------------
# Campaign copy / voice DNA
# ---------------------------------------------------------------------------

def test_seven_touches_and_cadence():
    assert len(campaign.TOUCHES) == 7
    assert [t["day"] for t in campaign.TOUCHES] == [0, 2, 4, 7, 10, 14, 21]
    assert [t["channel"] for t in campaign.TOUCHES] == \
        ["email", "email", "email", "sms", "email", "email", "sms"]


def test_campaign_passes_voice_validation():
    report = campaign.validate_touches()
    assert report["ok"], report["problems"]


def test_no_banned_words_anywhere():
    for t in campaign.TOUCHES:
        assert campaign.check_banned(f"{t.get('subject','')} {t['body']}") == []


def test_cta_in_touches_three_to_seven():
    for t in campaign.TOUCHES:
        if t["order"] >= 3:
            low = t["body"].lower()
            assert "book" in low or "reply" in low


def test_booking_link_substitution():
    rendered = campaign.render_touches("https://book.example/eva")
    joined = " ".join(t["body"] for t in rendered)
    assert "https://book.example/eva" in joined
    assert campaign.BOOKING_PLACEHOLDER not in joined


def test_landing_url_in_touch_one():
    assert campaign.LANDING_URL in campaign.TOUCHES[0]["body"]


# ---------------------------------------------------------------------------
# Ledger immutability (the trigger)
# ---------------------------------------------------------------------------

def test_lead_ledger_blocks_identity_update(db):
    eid = memory.record_lead_event(event_type=memory.EVENT_LEAD_CAPTURED,
                                   contact_id="c1", email="a@b.com", path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE lead_events SET email = 'x@y.com' WHERE event_id = ?",
                         (eid,))
            conn.commit()
    finally:
        conn.close()


def test_lead_ledger_blocks_delete(db):
    eid = memory.record_lead_event(event_type=memory.EVENT_TOUCH_SENT,
                                   contact_id="c1", path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM lead_events WHERE event_id = ?", (eid,))
            conn.commit()
    finally:
        conn.close()


def test_lead_ledger_correction_supersedes(db):
    first = memory.record_lead_event(event_type=memory.EVENT_LEAD_ENGAGED,
                                     contact_id="c1", email="a@b.com", path=db)
    memory.record_lead_event(event_type=memory.EVENT_LEAD_ENGAGED, contact_id="c1",
                             email="a@b.com", summary="correction",
                             supersedes_event_id=first, path=db)
    rows = {e["event_id"]: e for e in memory.list_lead_events(contact_id="c1", path=db)}
    assert rows[first]["status"] == memory.STATUS_SUPERSEDED


def test_funnel_artifacts_append_only(db):
    aid = memory.record_artifact(kind=memory.ARTIFACT_PIPELINE, name="Eva Acquisition",
                                 external_id="pipe_1", path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE funnel_artifacts SET name = 'x' WHERE id = ?", (aid,))
            conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM funnel_artifacts WHERE id = ?", (aid,))
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Funnel build (Part 1) — idempotency
# ---------------------------------------------------------------------------

def test_build_funnel_creates_all_pieces(svc):
    result = svc.build_funnel()
    assert result["pipeline"]["name"] == "Eva Acquisition"
    assert [s["name"] for s in result["pipeline"]["stages"]] == \
        ["Lead", "Engaged", "Demo Booked", "Demo Held", "Closed"]
    assert result["booking_link"]
    assert result["template_count"] == 7
    # nothing needs manual setup when the stub supports everything
    assert result["manual_required"] == []
    kinds = {c["kind"] for c in result["created"]}
    assert {"pipeline", "calendar", "custom_field", "template", "workflow"} <= kinds


def test_build_funnel_is_idempotent(svc):
    first = svc.build_funnel()
    assert len(first["created"]) >= 10  # 5 fixed + 7 templates - overlaps
    second = svc.build_funnel()
    # Second run creates nothing new; everything is skipped.
    assert second["created"] == []
    assert len(second["skipped"]) >= 10


def test_build_funnel_degrades_when_workflow_ui_only(db):
    ghl = StubGHLClient(workflow_supported=False, template_supported=False)
    svc = GHLAgentService(db_path=db, ghl=ghl, state=StubStateLedgerClient(),
                          offline=True)
    result = svc.build_funnel()
    manual_kinds = {m["kind"] for m in result["manual_required"]}
    assert "workflow" in manual_kinds
    assert "template" in manual_kinds
    # The build still succeeds for the pieces GHL does support.
    assert result["pipeline"]["name"] == "Eva Acquisition"
    assert result["booking_link"]


def test_funnel_status_reflects_build(svc):
    before = svc.funnel_status()
    assert before["built"] is False
    svc.build_funnel()
    after = svc.funnel_status()
    assert after["built"] is True
    assert after["pipeline"]["exists"] is True
    assert after["calendar"]["exists"] is True
    assert all(v["exists"] for v in after["templates"].values())


# ---------------------------------------------------------------------------
# Lead-capture loop (Part 2)
# ---------------------------------------------------------------------------

def test_capture_lead_full_loop(svc):
    svc.build_funnel()
    state = svc.state
    result = svc.capture_lead(email="lead@example.com", name="Jane Buyer")
    assert result["status"] == "captured"
    assert result["contact_id"]
    assert result["pipeline_stage"] == "Lead"

    # Contact exists in GHL with the acquisition tag.
    contact = svc.ghl.contacts["lead@example.com"]
    assert ACQUISITION_TAG in contact["tags"]
    # Dropped into the pipeline.
    assert svc.ghl.opportunities
    # Enrolled in the workflow.
    assert svc.ghl.workflow_enrollments

    # Local ledger has a lead_captured event.
    events = svc.lead_events(email="lead@example.com")
    assert any(e["event_type"] == memory.EVENT_LEAD_CAPTURED for e in events)
    # State ledger got the emission.
    assert any(e["event_type"] == memory.EVENT_LEAD_CAPTURED for e in state.events)


def test_capture_requires_email_or_phone(svc):
    from service import CaptureError
    with pytest.raises(CaptureError):
        svc.capture_lead(email="", phone="")


def test_capture_is_idempotent_on_contact(svc):
    svc.build_funnel()
    a = svc.capture_lead(email="dup@example.com", name="Dup")
    b = svc.capture_lead(email="dup@example.com", name="Dup")
    assert a["contact_id"] == b["contact_id"]
    # No duplicate opportunity for the same contact+pipeline.
    assert len(svc.ghl.opportunities) == 1


# ---------------------------------------------------------------------------
# Webhook -> lead-lifecycle mapping + state emission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("email_opened", memory.EVENT_LEAD_ENGAGED),
    ("appointment_booked", memory.EVENT_DEMO_BOOKED),
    ("appointment_showed", memory.EVENT_DEMO_HELD),
    ("opportunity_won", memory.EVENT_CLOSED),
    ("sms_sent", memory.EVENT_TOUCH_SENT),
])
def test_webhook_maps_events(svc, raw, expected):
    res = svc.handle_webhook({"type": raw, "contact_id": "c9", "email": "w@x.com"})
    assert res["ok"] is True
    assert res["event_type"] == expected
    assert any(e["event_type"] == expected for e in svc.lead_events(contact_id="c9"))
    assert any(e["event_type"] == expected for e in svc.state.events)


def test_webhook_ignores_unmapped(svc):
    res = svc.handle_webhook({"type": "some_unknown_event"})
    assert res["ok"] is False
    assert res["ignored"] is True


def test_webhook_reads_nested_contact(svc):
    res = svc.handle_webhook(
        {"event": "reply", "contact": {"id": "c42", "email": "n@e.com"}})
    assert res["ok"] is True
    assert res["contact_id"] == "c42"
    assert res["event_type"] == memory.EVENT_LEAD_ENGAGED


# ---------------------------------------------------------------------------
# GHL client contract (stub)
# ---------------------------------------------------------------------------

def test_stub_upsert_requires_identifier():
    ghl = StubGHLClient()
    with pytest.raises(ValueError):
        ghl.upsert_contact(email="", phone="")


def test_stub_create_pipeline_idempotent():
    ghl = StubGHLClient()
    a = ghl.create_pipeline("P", ["Lead", "Closed"])
    b = ghl.create_pipeline("P", ["Lead", "Closed"])
    assert a["action"] == "created"
    assert b["action"] == "skipped"
    assert len(ghl.list_pipelines()) == 1
