"""Baseline offline tests for social-publish store + credential detection (no network)."""

import os
import tempfile

os.environ["SOCIAL_PUBLISH_DB"] = os.path.join(tempfile.mkdtemp(), "social_publish_test.db")

import store  # noqa: E402
import credentials  # noqa: E402


def test_create_and_get_draft_roundtrip():
    d = store.create_draft("hello world", platforms=["linkedin"])
    assert d["status"] == store.STATUS_PENDING
    assert d["text"] == "hello world"
    assert d["platforms"] == ["linkedin"]
    got = store.get_draft(d["id"])
    assert got["id"] == d["id"]


def test_list_and_update_draft():
    d = store.create_draft("draft to approve")
    updated = store.update_draft(d["id"], {"status": store.STATUS_APPROVED,
                                           "approval_actor": "tester"})
    assert updated["status"] == store.STATUS_APPROVED
    assert updated["approval_actor"] == "tester"
    approved = store.list_drafts(status=store.STATUS_APPROVED)
    assert any(x["id"] == d["id"] for x in approved)


def test_get_missing_draft_returns_none():
    assert store.get_draft("does-not-exist") is None


def test_credentials_detect_shape(monkeypatch):
    # No config file and no env → both platforms report not-configured.
    monkeypatch.setattr(credentials, "CHANNELS_CONFIG_PATH",
                        __import__("pathlib").Path("/nonexistent/channels_config.json"))
    for var in list(credentials.LINKEDIN_ENV.values()) + list(credentials.X_ENV.values()):
        monkeypatch.delenv(var, raising=False)
    rep = credentials.detect()
    assert "linkedin" in rep and "x" in rep
    assert rep["linkedin"]["configured"] is False
    assert rep["x"]["configured"] is False
    assert rep["all_configured"] is False
