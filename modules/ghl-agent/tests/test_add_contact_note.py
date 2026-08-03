"""Tests for StubGHLClient.add_contact_note (new method for call-capture sync)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghl_client import StubGHLClient  # noqa: E402


def test_add_contact_note_success():
    ghl = StubGHLClient()
    contact = ghl.upsert_contact(email="lead@example.com", name="Lead")
    res = ghl.add_contact_note(contact["id"], "Called about Mission Villa terms.")
    assert res["ok"] is True
    assert res["contact_id"] == contact["id"]
    assert res["body"] == "Called about Mission Villa terms."


def test_add_contact_note_unknown_contact_fails_cleanly():
    ghl = StubGHLClient()
    res = ghl.add_contact_note("contact_doesnotexist", "note body")
    assert res["ok"] is False
    assert "unknown contact" in res["error"]


def test_add_contact_note_appends_multiple_notes():
    ghl = StubGHLClient()
    contact = ghl.upsert_contact(email="multi@example.com", name="Multi")
    ghl.add_contact_note(contact["id"], "First call.")
    ghl.add_contact_note(contact["id"], "Second call.")
    stored = ghl.contacts["multi@example.com"]["notes"]
    assert len(stored) == 2
    assert stored[0]["body"] == "First call."
    assert stored[1]["body"] == "Second call."
