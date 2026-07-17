"""Baseline offline tests for pathfinder db + outreach sequences + api (no network)."""

import os
import tempfile

import pathfinder_db
import outreach_sequences as seq


def _fresh_db(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "pathfinder_test.db")
    monkeypatch.setattr(pathfinder_db, "DB_PATH", path)
    pathfinder_db.init_db()


def test_insert_and_get_lead(monkeypatch):
    _fresh_db(monkeypatch)
    lead_id = pathfinder_db.insert_lead("Jane", "jane@example.com", "Acme",
                                        "enterprise", "acquisition", 90, "high-touch")
    lead = pathfinder_db.get_lead_by_id(lead_id)
    assert lead["name"] == "Jane"
    assert lead["stage"] == "new"


def test_advance_lead_stage(monkeypatch):
    _fresh_db(monkeypatch)
    lead_id = pathfinder_db.insert_lead("Bob", "bob@example.com", None,
                                        "operator", None, 50, "standard")
    updated = pathfinder_db.advance_lead_stage(lead_id)
    assert updated["stage"] == "contacted"


def test_get_sequence_and_first_dm():
    s = seq.get_sequence("high-touch")
    assert s is not None and s["first_dm"] == 1
    first = seq.get_first_dm("high-touch")
    assert first["dm_number"] == 1 and first["body"]


def test_get_next_action_due():
    action = seq.get_next_action("high-touch", days_since_entry=3)
    assert action is not None and action["day"] <= 3


def test_get_next_action_none_before_first():
    assert seq.get_next_action("standard", days_since_entry=0) is None


def test_api_health_and_scoring():
    import pytest
    # pathfinder_api declares a pydantic EmailStr field; skip cleanly if the
    # optional email-validator dependency is not installed in the offline env.
    pathfinder_api = pytest.importorskip("pathfinder_api")
    from fastapi.testclient import TestClient

    client = TestClient(pathfinder_api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    score, sequence = pathfinder_api.score_lead("enterprise", "acquisition")
    assert isinstance(score, int) and isinstance(sequence, str)
