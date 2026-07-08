"""
Offline test suite for the EVA Channels module (spec section 8).

No network, no real Reddit/Substack calls. Every test builds a fresh service
backed by a throwaway SQLite file and injects Stub / fake-success publishers, so
runs are fully isolated and sandbox-safe. Runs two ways:

    python test_channels.py      # standalone runner, prints PASS/FAIL
    pytest test_channels.py      # if pytest is installed
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from database import Store
from publisher import (
    PublishResult,
    RedditPublisher,
    StubPublisher,
    SubstackPublisher,
)
from service import ChannelsService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_store() -> Store:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-channels-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return Store(path)


def _service(publishers=None) -> ChannelsService:
    return ChannelsService(store=_fresh_store(), publishers=publishers)


def _not_wired_service() -> ChannelsService:
    """A service whose transports are honest, not-wired stubs (ok=False)."""
    return _service({
        "reddit": StubPublisher("reddit", fake_success=False),
        "substack": StubPublisher("substack", fake_success=False),
    })


def _fake_success_service() -> tuple[ChannelsService, StubPublisher]:
    """A service whose transports are fake-success stubs (ok=True)."""
    stub = StubPublisher("reddit", fake_success=True)
    svc = _service({
        "reddit": stub,
        "substack": StubPublisher("substack", fake_success=True),
    })
    return svc, stub


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _mk(svc, platform="reddit", title="Hello", body="World") -> dict:
    return svc.create_item({"platform": platform, "title": title, "body": body})


# ---------------------------------------------------------------------------
# Schema + ledger
# ---------------------------------------------------------------------------

def test_schema_creates_all_tables():
    store = _fresh_store()
    with store._connect() as conn:
        names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for expected in {
        "channel_items", "channel_platform_config", "channel_schedule",
        "channels_ledger", "memory",
    }:
        assert expected in names, f"missing table {expected}"


def test_ledger_is_append_only():
    svc = _not_wired_service()
    _mk(svc)
    rows = svc.query_ledger()
    assert len(rows) >= 1
    row_id = rows[0]["id"]

    conn = svc.store._connect()
    try:
        raised_update = False
        try:
            conn.execute(
                "UPDATE channels_ledger SET actor='tamper' WHERE id=?", (row_id,)
            )
            conn.commit()
        except Exception:
            raised_update = True
        assert raised_update, "ledger UPDATE must be blocked"

        raised_delete = False
        try:
            conn.execute("DELETE FROM channels_ledger WHERE id=?", (row_id,))
            conn.commit()
        except Exception:
            raised_delete = True
        assert raised_delete, "ledger DELETE must be blocked"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# StubPublisher: not-wired path + fake-success path
# ---------------------------------------------------------------------------

def test_stub_not_wired_returns_ok_false_no_network():
    stub = StubPublisher("reddit", fake_success=False)
    result = stub.publish({"id": "x", "platform": "reddit"})
    assert result.ok is False
    assert result.provider == "reddit"
    assert result.error  # a clear, non-empty error


def test_stub_fake_success_returns_ok_true_with_url():
    stub = StubPublisher("reddit", fake_success=True)
    result = stub.publish({"id": "abc", "platform": "reddit"})
    assert result.ok is True
    assert result.provider == "reddit"
    assert result.post_url  # synthetic url for the posted path


# ---------------------------------------------------------------------------
# Approval + publish gate
# ---------------------------------------------------------------------------

def test_approve_flips_status_and_appends_ledger():
    svc = _not_wired_service()
    item = _mk(svc)
    assert item["status"] == "draft"
    approved = svc.approve_item(item["id"], actor="founder")
    assert approved["status"] == "approved"
    events = [e["event_type"] for e in svc.query_ledger()]
    assert "item_approved" in events


def test_publish_rejects_draft_item():
    svc, _ = _fake_success_service()
    item = _mk(svc)  # draft, never approved
    out = svc.publish_item(item["id"], actor="test")
    assert out["result"]["ok"] is False
    assert "not approved" in out["result"]["error"]
    # Status unchanged; nothing posted.
    assert svc.get_item(item["id"])["status"] == "draft"
    events = [e["event_type"] for e in svc.query_ledger()]
    assert "publish_rejected" in events


def test_publish_approved_via_not_wired_stub_sets_failed():
    svc = _not_wired_service()
    item = _mk(svc)
    svc.approve_item(item["id"])
    out = svc.publish_item(item["id"], actor="test")
    assert out["result"]["ok"] is False
    updated = svc.get_item(item["id"])
    assert updated["status"] == "failed"
    assert updated["error"]
    events = [e["event_type"] for e in svc.query_ledger()]
    assert "item_failed" in events


def test_publish_approved_via_fake_success_sets_posted():
    svc, stub = _fake_success_service()
    item = _mk(svc)
    svc.approve_item(item["id"])
    out = svc.publish_item(item["id"], actor="test")
    assert out["result"]["ok"] is True
    updated = svc.get_item(item["id"])
    assert updated["status"] == "posted"
    assert updated["post_url"]
    assert updated["posted_at"]
    assert len(stub.posted) == 1
    events = [e["event_type"] for e in svc.query_ledger()]
    assert "item_posted" in events


def test_republish_is_idempotent_noop():
    svc, stub = _fake_success_service()
    item = _mk(svc)
    svc.approve_item(item["id"])
    first = svc.publish_item(item["id"], actor="test")
    url = first["result"]["post_url"]
    assert len(stub.posted) == 1

    # Re-publish the already-posted item: no second post, same url returned.
    second = svc.publish_item(item["id"], actor="test")
    assert second["result"].get("noop") is True
    assert second["result"]["post_url"] == url
    assert len(stub.posted) == 1  # not incremented
    assert svc.get_item(item["id"])["status"] == "posted"


# ---------------------------------------------------------------------------
# Scheduler tick
# ---------------------------------------------------------------------------

def test_tick_noop_when_nothing_approved_due():
    svc, stub = _fake_success_service()
    _mk(svc)  # draft only, nothing approved
    result = svc.tick(actor="test")
    assert result["posted"] is None
    assert result["reason"] == "no_due_item"
    assert len(stub.posted) == 0


def test_tick_posts_next_approved_due_and_advances_next_due():
    svc, stub = _fake_success_service()
    svc.update_schedule({"cadence_days": 3, "next_due": _past_iso()}, actor="test")
    item = _mk(svc)
    svc.approve_item(item["id"])

    before = svc.get_schedule()["next_due"]
    result = svc.tick(actor="test")
    assert result["posted"] is not None
    assert result["posted"]["status"] == "posted"
    assert len(stub.posted) == 1

    after = svc.get_schedule()["next_due"]
    assert after != before
    delta = datetime.fromisoformat(after) - datetime.fromisoformat(before)
    assert delta == timedelta(days=3)


def test_tick_before_next_due_posts_nothing():
    svc, stub = _fake_success_service()
    svc.update_schedule({"next_due": _future_iso()}, actor="test")
    item = _mk(svc)
    svc.approve_item(item["id"])
    result = svc.tick(actor="test")
    assert result["posted"] is None
    assert result["reason"] == "not_due"
    assert len(stub.posted) == 0
    assert svc.get_item(item["id"])["status"] == "approved"


# ---------------------------------------------------------------------------
# Platform chokepoints (real path, offline)
# ---------------------------------------------------------------------------

def test_substack_always_needs_manual_publish_never_ok():
    # Real SubstackPublisher shells out to substack_post.py (no network).
    export_dir = tempfile.mkdtemp(prefix="eva-substack-")
    os.environ["EVA_CHANNELS_SUBSTACK_DIR"] = export_dir
    try:
        svc = _service({
            "reddit": StubPublisher("reddit"),
            "substack": SubstackPublisher(config={"publication_url": "https://x.substack.com"}),
        })
        item = _mk(svc, platform="substack", title="My Post", body="Body text")
        svc.approve_item(item["id"])
        out = svc.publish_item(item["id"], actor="test")
        assert out["result"]["ok"] is False
        assert out["result"]["needs_manual_publish"] is True
        assert "no public posting API" in out["result"]["error"]
        # A markdown draft was exported to disk.
        files = [f for f in os.listdir(export_dir) if f.endswith(".md")]
        assert files, "substack_post.py must export a markdown draft"
        assert svc.get_item(item["id"])["status"] == "failed"
    finally:
        os.environ.pop("EVA_CHANNELS_SUBSTACK_DIR", None)


def test_reddit_not_wired_returns_credentials_not_set():
    # Real RedditPublisher shells out to reddit_post.py with no creds set.
    for env in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        os.environ.pop(env, None)
    publisher = RedditPublisher(config={"subreddit": "r/test"})
    result = publisher.publish({"id": "1", "platform": "reddit", "title": "t", "body": "b"})
    assert result.ok is False
    assert result.provider == "reddit"
    assert "credentials not set" in result.error


# ---------------------------------------------------------------------------
# Agent intelligence layer
# ---------------------------------------------------------------------------

def test_memory_read_write():
    svc = _not_wired_service()
    svc.set_memory("greeting", "hello", source="test")
    got = svc.get_memory("greeting")
    assert got is not None
    assert got["value"] == "hello"
    assert got["source"] == "test"
    # Upsert overwrites.
    svc.set_memory("greeting", "hi", source="test")
    assert svc.get_memory("greeting")["value"] == "hi"


def test_mission_and_goals_graceful_no_op_when_absent():
    # Point at non-existent files: must not crash, returns empty strings.
    os.environ["EVA_MISSION_PATH"] = "/tmp/does-not-exist-mission.md"
    os.environ["EVA_GOALS_PATH"] = "/tmp/does-not-exist-goals.md"
    try:
        svc = _not_wired_service()
        docs = svc.read_mission_and_goals()
        assert docs["mission"] == ""
        assert docs["current_goals"] == ""
    finally:
        os.environ.pop("EVA_MISSION_PATH", None)
        os.environ.pop("EVA_GOALS_PATH", None)


def test_status_reports_counts_and_last_run():
    svc, _ = _fake_success_service()
    a = _mk(svc)
    svc.approve_item(a["id"])
    b = _mk(svc)
    svc.approve_item(b["id"])
    svc.publish_item(a["id"])  # -> posted
    st = svc.status()
    assert st["providers"] == ["reddit", "substack"]
    assert st["posted_count"] == 1
    assert st["pending_approved"] == 1
    assert st["last_run"]  # last_run memory written on publish
    assert json.loads(st["last_run"])["ok"] is True


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def test_integration_create_approve_publish():
    svc, stub = _fake_success_service()
    item = svc.create_item({"platform": "reddit", "title": "Launch", "body": "We are live"})
    svc.approve_item(item["id"], actor="founder")
    out = svc.publish_item(item["id"], actor="cron")
    assert out["item"]["status"] == "posted"
    assert out["result"]["post_url"]
    posted_events = [e for e in svc.query_ledger() if e["event_type"] == "item_posted"]
    assert len(posted_events) == 1
    assert posted_events[0]["entity_id"] == item["id"]


def test_integration_config_set_then_not_wired_publish_fails():
    svc = _service({
        "reddit": RedditPublisher(),
        "substack": StubPublisher("substack"),
    })
    for env in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        os.environ.pop(env, None)
    svc.update_config("reddit", {"subreddit": "r/Entrepreneur"}, actor="test")
    item = _mk(svc)
    svc.approve_item(item["id"])
    out = svc.publish_item(item["id"], actor="test")
    assert out["result"]["ok"] is False
    assert svc.get_item(item["id"])["status"] == "failed"
    events = [e["event_type"] for e in svc.query_ledger()]
    assert "item_failed" in events


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [v for k, v in sorted(globals().items())
            if k.startswith("test_") and callable(v)]


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
