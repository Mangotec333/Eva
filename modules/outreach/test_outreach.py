"""
Offline test suite for the EVA Outreach module (spec section 8).

No network, no real email, no external deps beyond the standard library +
pydantic. Runs two ways:

    python test_outreach.py        # standalone runner, prints PASS/FAIL
    pytest test_outreach.py        # if pytest is installed

Every test builds a fresh service backed by a throwaway SQLite file and the
StubSender, so runs are fully isolated.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

from database import Store
from sender import GmailSender, OutboundMessage, StubSender
from service import ComplianceError, OutreachService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> tuple[OutreachService, StubSender]:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-outreach-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    sender = StubSender()
    svc = OutreachService(store=Store(path), sender=sender)
    return svc, sender


def _contact(svc, email="investor@example.com", relationship_type="warm") -> dict:
    return svc.add_contact(
        {"email": email, "name": "Test Investor", "relationship_type": relationship_type}
    )


def _campaign(svc) -> dict:
    return svc.create_campaign(
        {
            "name": "Seed round",
            "subject": "Investment opportunity",
            "body": "Hello, would you like to invest?",
            "sender_name": "Founder",
            "sender_email": "founder@eva.example",
            "sender_address": "123 Market St",
            "disclosures_text": "This is not an offer. Consult your advisor.",
        }
    )


def _add_recipient(svc, campaign_id, contact_id) -> dict:
    result = svc.add_recipients(campaign_id, [contact_id], actor="test")
    both = result["added"] + result["excluded"]
    return both[0]


# ---------------------------------------------------------------------------
# Unit tests (spec section 8)
# ---------------------------------------------------------------------------

def test_recipient_add_excludes_suppressed():
    svc, _ = _fresh_service()
    contact = _contact(svc, email="opt@x.com")
    svc.add_suppression("opt@x.com", reason="opt_out", source="test")
    campaign = _campaign(svc)

    result = svc.add_recipients(campaign["id"], [contact["id"]], actor="test")
    assert len(result["added"]) == 0
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["status"] == "suppressed"

    events = [e["event_type"] for e in svc.query_ledger()]
    assert "recipient_suppressed_excluded" in events


def test_send_blocked_when_not_approved():
    svc, sender = _fresh_service()
    contact = _contact(svc)
    campaign = _campaign(svc)
    rec = _add_recipient(svc, campaign["id"], contact["id"])

    try:
        svc.send_recipient(rec["id"], actor="test")
        assert False, "expected ComplianceError for un-approved send"
    except ComplianceError as exc:
        assert exc.code == "not_approved"
    assert len(sender.sent) == 0


def test_send_blocked_when_suppressed():
    svc, sender = _fresh_service()
    contact = _contact(svc, email="later-optout@x.com")
    campaign = _campaign(svc)
    rec = _add_recipient(svc, campaign["id"], contact["id"])
    svc.approve_recipient(rec["id"], approved_by="founder")

    # Opt out AFTER approval — send must still be blocked.
    svc.add_suppression("later-optout@x.com", reason="opt_out", source="test")
    try:
        svc.send_recipient(rec["id"], actor="test")
        assert False, "expected ComplianceError for suppressed send"
    except ComplianceError as exc:
        assert exc.code == "suppressed"
    assert len(sender.sent) == 0


def test_sale_blocked_for_cold_without_verification():
    svc, _ = _fresh_service()
    contact = _contact(svc, email="cold@x.com", relationship_type="cold")
    try:
        svc.record_sale(contact["id"], amount=50000, actor="test")
        assert False, "expected ComplianceError for cold unverified sale"
    except ComplianceError as exc:
        assert exc.code == "not_verified"


def test_optout_in_ledger_and_blocks_future_sends():
    svc, sender = _fresh_service()
    contact = _contact(svc, email="block@x.com")
    campaign = _campaign(svc)
    rec = _add_recipient(svc, campaign["id"], contact["id"])
    svc.approve_recipient(rec["id"], approved_by="founder")

    svc.add_suppression("block@x.com", reason="unsubscribe reply", source="test")
    opt_events = [e for e in svc.query_ledger() if e["event_type"] == "opt_out"]
    assert len(opt_events) == 1

    try:
        svc.send_recipient(rec["id"], actor="test")
        assert False
    except ComplianceError as exc:
        assert exc.code == "suppressed"
    assert len(sender.sent) == 0


def test_verification_expiry_flips_status_and_blocks_sale():
    svc, _ = _fresh_service()
    contact = _contact(svc, email="expired@x.com", relationship_type="cold")
    case = svc.create_verification(contact["id"], method="third_party")
    svc.advance_verification(case["id"], "documents_received", actor="test")
    svc.advance_verification(case["id"], "verified", verifier="CPA Jane", actor="test")

    # Sale is allowed while verification is valid.
    svc.record_sale(contact["id"], amount=25000, actor="test")

    # Backdate expiry into the past, then a read must flip it to expired.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    svc.store.update_verification(case["id"], {"expires_at": past})

    refreshed = svc.get_verification(case["id"])
    assert refreshed["status"] == "expired"

    try:
        svc.record_sale(contact["id"], amount=25000, actor="test")
        assert False, "expected sale block after expiry"
    except ComplianceError as exc:
        assert exc.code == "not_verified"

    events = [e["event_type"] for e in svc.query_ledger()]
    assert "verification_expired" in events


def test_ledger_is_append_only():
    svc, _ = _fresh_service()
    _contact(svc)  # produces at least one ledger row
    rows = svc.query_ledger()
    assert len(rows) >= 1
    row_id = rows[0]["id"]

    conn = svc.store._connect()
    try:
        raised_update = False
        try:
            conn.execute(
                "UPDATE compliance_ledger SET actor = 'tamper' WHERE id = ?", (row_id,)
            )
            conn.commit()
        except Exception:
            raised_update = True
        assert raised_update, "ledger UPDATE must be blocked"

        raised_delete = False
        try:
            conn.execute("DELETE FROM compliance_ledger WHERE id = ?", (row_id,))
            conn.commit()
        except Exception:
            raised_delete = True
        assert raised_delete, "ledger DELETE must be blocked"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Integration tests (spec section 8)
# ---------------------------------------------------------------------------

def test_integration_happy_path():
    svc, sender = _fresh_service()
    contact = _contact(svc, email="warm@x.com", relationship_type="warm")
    campaign = _campaign(svc)
    rec = _add_recipient(svc, campaign["id"], contact["id"])

    svc.approve_recipient(rec["id"], approved_by="founder")
    sent = svc.send_recipient(rec["id"], actor="founder")

    assert sent["status"] == "sent"
    assert sent["sent_at"]
    assert len(sender.sent) == 1
    assert sender.sent[0].to_email == "warm@x.com"

    sent_events = [e for e in svc.query_ledger() if e["event_type"] == "sent"]
    assert len(sent_events) == 1
    details = sent_events[0]["details"]
    assert details["approved_by"] == "founder"
    assert details["disclosures_hash"]


def test_integration_optout_then_resend_blocked():
    svc, sender = _fresh_service()
    contact = _contact(svc, email="reoptout@x.com", relationship_type="warm")
    campaign = _campaign(svc)
    rec = _add_recipient(svc, campaign["id"], contact["id"])
    svc.approve_recipient(rec["id"], approved_by="founder")

    svc.send_recipient(rec["id"], actor="founder")
    assert len(sender.sent) == 1

    svc.add_suppression("reoptout@x.com", reason="opt_out", source="test")
    try:
        svc.send_recipient(rec["id"], actor="founder")
        assert False
    except ComplianceError as exc:
        assert exc.code == "suppressed"
    assert len(sender.sent) == 1  # no additional send


def test_integration_verify_unblocks_sale():
    svc, _ = _fresh_service()
    contact = _contact(svc, email="verifyme@x.com", relationship_type="cold")

    try:
        svc.record_sale(contact["id"], amount=100000, actor="test")
        assert False
    except ComplianceError as exc:
        assert exc.code == "not_verified"

    case = svc.create_verification(contact["id"], method="accreditation_letter")
    svc.advance_verification(case["id"], "documents_received", actor="test")
    svc.advance_verification(case["id"], "verified", verifier="CPA Bob", actor="test")

    entry = svc.record_sale(contact["id"], amount=100000, actor="test")
    assert entry["event_type"] == "sale_recorded"


# ---------------------------------------------------------------------------
# GmailSender (subprocess helper wiring) — no real network, verifies the
# contract: it shells out, parses JSON, and never silently fakes success.
# ---------------------------------------------------------------------------

def test_gmail_sender_reports_unwired_host():
    """On a host where gmail_send.py has no real transport wired, the sender
    must return ok=False with a clear error — never silently succeed."""
    import json

    msg = OutboundMessage(
        to_email="investor@example.com",
        to_name="Test Investor",
        subject="Test",
        body="Hello",
        disclosures_text="disclosures",
        sender_name="Founder",
        sender_email="founder@example.com",
        sender_address="Porter Ranch, CA",
        campaign_id="c1",
        recipient_id="r1",
    )
    sender = GmailSender()
    result = sender.send(msg)
    assert result.provider == "gmail"
    assert result.ok is False, "GmailSender must not silently fake a send on an unwired host"
    assert result.error, "GmailSender must return a clear error when transport is unwired"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    passed, failed = 0, 0
    for test in _all_tests():
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
