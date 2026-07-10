"""
Offline test suite for the EVA LinkedIn Analytics module (spec section 8).

No network, no real LinkedIn call. Every test uses either the offline
``StubAnalyticsClient`` (which returns ok=False and touches no network) or a
``FakeSuccessAnalyticsClient`` test double that injects deterministic sample
posts to exercise the upsert path. Stubs never fake success — the fake-success
client is a test double, not a production transport.

Runs two ways:

    python test_linkedin_analytics.py    # standalone runner, prints PASS/FAIL
    pytest test_linkedin_analytics.py    # if pytest is installed

Every test builds a fresh service backed by a throwaway SQLite file, so runs
are fully isolated.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from client import FetchResult, PostMetrics, StubAnalyticsClient
from database import Store
from service import LinkedInAnalyticsService, compute_engagement_rate


# ---------------------------------------------------------------------------
# Test doubles / fixtures
# ---------------------------------------------------------------------------

class FakeSuccessAnalyticsClient:
    """Injects deterministic sample posts to exercise the upsert path. This is
    a TEST DOUBLE — production stubs never fake success."""

    name = "linkedin"

    def __init__(self, posts: list[PostMetrics]):
        self._posts = posts
        self.calls = 0

    def fetch(self, author_urn: str, window_days: int) -> FetchResult:
        self.calls += 1
        return FetchResult(ok=True, provider=self.name, posts=list(self._posts),
                           error="")


def _fresh_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-lianalytics-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return path


def _fresh_service(client=None):
    path = _fresh_db_path()
    store = Store(path)
    svc = LinkedInAnalyticsService(store=store, client=client or StubAnalyticsClient())
    return svc, store


def _sample_posts(impr=1000, reactions=50, comments=20, shares=10, clicks=30):
    return [
        PostMetrics(
            post_urn="urn:li:ugcPost:111",
            share_urn="urn:li:share:111",
            author_urn="urn:li:organization:999",
            posted_at="2026-07-01T12:00:00+00:00",
            text="First sample post about Eva.",
            post_url="https://www.linkedin.com/feed/update/urn:li:ugcPost:111",
            impressions=impr,
            unique_impressions=int(impr * 0.8),
            clicks=clicks,
            reactions=reactions,
            comments=comments,
            shares=shares,
            raw={"source": "fake"},
        ),
        PostMetrics(
            post_urn="urn:li:ugcPost:222",
            share_urn="urn:li:share:222",
            author_urn="urn:li:organization:999",
            posted_at="2026-07-02T12:00:00+00:00",
            text="Second sample post.",
            post_url="https://www.linkedin.com/feed/update/urn:li:ugcPost:222",
            impressions=impr * 3,
            unique_impressions=int(impr * 3 * 0.8),
            clicks=clicks * 2,
            reactions=reactions * 2,
            comments=comments,
            shares=shares,
            raw={"source": "fake"},
        ),
    ]


def _fixed_now():
    return datetime(2026, 7, 8, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Schema + ledger
# ---------------------------------------------------------------------------

def test_schema_creates_all_tables():
    _, store = _fresh_service()
    with store._connect() as conn:
        names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for expected in (
        "linkedin_posts",
        "linkedin_analytics",
        "linkedin_sync_config",
        "analytics_ledger",
        "memory",
    ):
        assert expected in names, f"missing table {expected}"


def test_ledger_is_append_only_update_rejected():
    _, store = _fresh_service()
    store.append_ledger("test_event", actor="test")
    rejected = False
    try:
        with store._connect() as conn:
            conn.execute("UPDATE analytics_ledger SET actor='x'")
    except sqlite3.IntegrityError:
        rejected = True
    except sqlite3.OperationalError as exc:
        rejected = "append-only" in str(exc)
    assert rejected, "UPDATE on analytics_ledger should be rejected by trigger"


def test_ledger_is_append_only_delete_rejected():
    _, store = _fresh_service()
    store.append_ledger("test_event", actor="test")
    rejected = False
    try:
        with store._connect() as conn:
            conn.execute("DELETE FROM analytics_ledger")
    except sqlite3.IntegrityError:
        rejected = True
    except sqlite3.OperationalError as exc:
        rejected = "append-only" in str(exc)
    assert rejected, "DELETE on analytics_ledger should be rejected by trigger"


# ---------------------------------------------------------------------------
# Stub client — no network, no fake success
# ---------------------------------------------------------------------------

def test_stub_fetch_returns_not_wired_and_makes_no_network_call():
    import socket

    stub = StubAnalyticsClient()

    # Poison the network: any socket creation during the stub call fails the test.
    original = socket.socket

    def _boom(*a, **k):
        raise AssertionError("StubAnalyticsClient must not open a socket")

    socket.socket = _boom
    try:
        result = stub.fetch("urn:li:organization:999", 28)
    finally:
        socket.socket = original

    assert result.ok is False
    assert result.provider == "stub"
    assert "not wired" in result.error
    assert result.posts == []


def test_sync_with_stub_returns_error_and_logs_attempt():
    svc, store = _fresh_service()
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    result = svc.sync(actor="test")
    assert result["ok"] is False
    assert "not wired" in result["error"]
    assert result["posts_synced"] == 0
    # The failed attempt is recorded in the append-only ledger.
    events = [r["event_type"] for r in store.query_ledger()]
    assert "sync_failed" in events


def test_sync_without_author_urn_is_skipped():
    svc, store = _fresh_service()
    result = svc.sync(actor="test")
    assert result["ok"] is False
    assert "author_urn" in result["error"]
    events = [r["event_type"] for r in store.query_ledger()]
    assert "sync_skipped" in events


# ---------------------------------------------------------------------------
# Fake-success sync — upsert + idempotency
# ---------------------------------------------------------------------------

def test_fake_success_sync_upserts_posts_and_snapshots():
    client = FakeSuccessAnalyticsClient(_sample_posts())
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    result = svc.sync(actor="test", now=_fixed_now())
    assert result["ok"] is True
    assert result["posts_synced"] == 2
    assert result["snapshots_upserted"] == 2
    assert store.count_posts() == 2
    assert store.count_snapshots() == 2
    events = [r["event_type"] for r in store.query_ledger()]
    assert "sync_completed" in events


def test_sync_twice_is_idempotent_no_duplicate_snapshots():
    client = FakeSuccessAnalyticsClient(_sample_posts())
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    now = _fixed_now()
    svc.sync(actor="test", now=now)
    svc.sync(actor="test", now=now)  # same day/window
    assert store.count_posts() == 2
    assert store.count_snapshots() == 2, "re-sync must not duplicate snapshots"


def test_resync_with_changed_metrics_updates_snapshot_and_appends_ledger():
    posts_v1 = _sample_posts(impr=1000, reactions=50)
    client = FakeSuccessAnalyticsClient(posts_v1)
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    now = _fixed_now()
    svc.sync(actor="test", now=now)

    # Metrics change; same window (same day) -> upsert in place.
    client._posts = _sample_posts(impr=5000, reactions=500)
    svc.sync(actor="test", now=now)

    assert store.count_snapshots() == 2, "changed metrics must update, not add"
    snaps = store.list_snapshots("urn:li:ugcPost:111")
    assert snaps[-1]["impressions"] == 5000
    assert snaps[-1]["reactions"] == 500

    # Two completed syncs -> two sync_completed ledger entries.
    completed = [
        r for r in store.query_ledger() if r["event_type"] == "sync_completed"
    ]
    assert len(completed) == 2


def test_engagement_rate_computed_correctly():
    # (reactions+comments+shares)/impressions = (50+20+10)/1000 = 0.08
    client = FakeSuccessAnalyticsClient(_sample_posts(impr=1000, reactions=50,
                                                       comments=20, shares=10))
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    svc.sync(actor="test", now=_fixed_now())
    snaps = store.list_snapshots("urn:li:ugcPost:111")
    assert abs(snaps[-1]["engagement_rate"] - 0.08) < 1e-9


def test_engagement_rate_guards_divide_by_zero():
    assert compute_engagement_rate(1, 2, 3, 0) == 0.0
    zero_post = [PostMetrics(post_urn="urn:li:ugcPost:z", impressions=0,
                             reactions=5, comments=5, shares=5)]
    client = FakeSuccessAnalyticsClient(zero_post)
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    svc.sync(actor="test", now=_fixed_now())
    snaps = store.list_snapshots("urn:li:ugcPost:z")
    assert snaps[-1]["engagement_rate"] == 0.0


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def test_tick_noop_when_not_configured():
    svc, store = _fresh_service()
    result = svc.tick(actor="cron")
    assert result["synced"] is False
    assert result["reason"] == "not_configured"
    assert store.count_snapshots() == 0


def test_tick_noop_when_not_due():
    client = FakeSuccessAnalyticsClient(_sample_posts())
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    svc.set_config({"next_due": future}, actor="test")
    result = svc.tick(actor="cron")
    assert result["synced"] is False
    assert result["reason"] == "not_due"
    assert store.count_snapshots() == 0


def test_tick_syncs_when_due():
    client = FakeSuccessAnalyticsClient(_sample_posts())
    svc, store = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    # next_due empty -> due immediately.
    result = svc.tick(actor="cron")
    assert result["synced"] is True
    assert result["result"]["ok"] is True
    assert store.count_snapshots() == 2


# ---------------------------------------------------------------------------
# Health / summary
# ---------------------------------------------------------------------------

def test_health_shape():
    svc, _ = _fresh_service()
    h = svc.health()
    assert set(h.keys()) == {
        "provider", "last_sync_at", "post_count", "snapshot_count"
    }
    assert h["post_count"] == 0
    assert h["snapshot_count"] == 0


def test_summary_returns_top_post():
    client = FakeSuccessAnalyticsClient(_sample_posts())
    svc, _ = _fresh_service(client=client)
    svc.set_config({"author_urn": "urn:li:organization:999"}, actor="test")
    svc.sync(actor="test", now=_fixed_now())
    s = svc.summary(days=28)
    assert s["post_count"] == 2
    assert s["snapshot_count"] == 2
    # Post 222 has 3x impressions -> it's the top post.
    assert s["top_post"]["post_urn"] == "urn:li:ugcPost:222"


# ---------------------------------------------------------------------------
# Agent intelligence layer — memory + mission/goals
# ---------------------------------------------------------------------------

def test_memory_read_write():
    svc, _ = _fresh_service()
    assert svc.memory_get("k") is None
    svc.memory_set("k", "v1", source="test")
    got = svc.memory_get("k")
    assert got["value"] == "v1"
    # Upsert on the same key.
    svc.memory_set("k", "v2", source="test")
    assert svc.memory_get("k")["value"] == "v2"
    assert len(svc.memory_all()) == 1


def test_mission_and_goals_absent_is_graceful_noop():
    svc, _ = _fresh_service()
    # Point at paths that certainly do not exist.
    import service as service_mod

    orig_mission, orig_goals = service_mod.MISSION_PATH, service_mod.GOALS_PATH
    service_mod.MISSION_PATH = "/nonexistent/does/not/exist/MISSION.md"
    service_mod.GOALS_PATH = "/nonexistent/does/not/exist/CURRENT_GOALS.md"
    try:
        a = svc.load_alignment()  # must not raise
    finally:
        service_mod.MISSION_PATH, service_mod.GOALS_PATH = orig_mission, orig_goals
    assert a["mission_present"] is False
    assert a["goals_present"] is False
    assert a["mission"] == ""
    assert a["goals"] == ""


def test_mission_present_when_file_exists():
    svc, _ = _fresh_service()
    import service as service_mod

    fd, path = tempfile.mkstemp(suffix=".md")
    os.write(fd, b"# Mission\nServe seniors.\n")
    os.close(fd)
    orig = service_mod.MISSION_PATH
    service_mod.MISSION_PATH = path
    try:
        a = svc.load_alignment()
    finally:
        service_mod.MISSION_PATH = orig
        os.unlink(path)
    assert a["mission_present"] is True
    assert "Mission" in a["mission"]


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]


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
