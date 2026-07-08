"""
Offline test suite for the EVA Postcards module (spec section 9).

No network, no real LinkedIn post. Rendering uses Pillow + the system DejaVu
fonts, so it runs fully offline. Runs two ways:

    python test_postcards.py      # standalone runner, prints PASS/FAIL
    pytest test_postcards.py      # if pytest is installed

Every test builds a fresh service backed by a throwaway SQLite file, a scratch
image dir, and the StubPublisher, so runs are fully isolated.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

from database import Store
from publisher import LinkedInPublisher, StubPublisher
from service import SEED_CARDS, PostcardsService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> tuple[PostcardsService, StubPublisher]:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-postcards-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    image_dir = tempfile.mkdtemp(prefix="eva-postcards-img-")
    publisher = StubPublisher()
    svc = PostcardsService(store=Store(path), publisher=publisher, image_dir=image_dir)
    return svc, publisher


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Unit tests (spec section 9)
# ---------------------------------------------------------------------------

def test_seed_is_idempotent():
    svc, _ = _fresh_service()
    first = svc.seed(actor="test")
    assert len(first["created"]) == len(SEED_CARDS)
    assert len(first["skipped"]) == 0

    second = svc.seed(actor="test")
    assert len(second["created"]) == 0
    assert len(second["skipped"]) == len(SEED_CARDS)

    # Running twice must not duplicate.
    assert len(svc.list_cards()) == len(SEED_CARDS)


def test_render_produces_png_with_nonzero_size():
    svc, _ = _fresh_service()
    card = svc.create_card(
        {"title": "Render test", "para1": "First paragraph.", "para2": "Second paragraph."}
    )
    path = card["image_path"]
    assert path and os.path.exists(path)
    assert os.path.getsize(path) > 0
    # PNG magic header.
    with open(path, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_tick_noop_when_nothing_due():
    svc, publisher = _fresh_service()
    svc.seed(actor="test")  # all drafts, none approved
    svc.update_schedule({"start_date": _past_iso(), "next_due": _past_iso()}, actor="test")

    result = svc.tick(actor="test")
    assert result["posted"] is None
    assert result["reason"] == "no_due_card"
    assert len(publisher.posted) == 0


def test_tick_posts_due_approved_card_and_advances_next_due():
    svc, publisher = _fresh_service()
    svc.seed(actor="test")
    svc.update_schedule(
        {"cadence_days": 3, "start_date": _past_iso(), "next_due": _past_iso()},
        actor="test",
    )
    card = svc.list_cards()[0]
    svc.approve_card(card["id"], actor="test")

    before = svc.get_schedule()["next_due"]
    result = svc.tick(actor="test")

    assert result["posted"] is not None
    assert result["posted"]["status"] == "posted"
    assert result["posted"]["posted_at"]
    assert len(publisher.posted) == 1

    after = svc.get_schedule()["next_due"]
    assert after != before
    delta = datetime.fromisoformat(after) - datetime.fromisoformat(before)
    assert delta == timedelta(days=3)


def test_tick_skips_draft_cards():
    svc, publisher = _fresh_service()
    svc.seed(actor="test")
    svc.update_schedule({"start_date": _past_iso(), "next_due": _past_iso()}, actor="test")

    # Nothing approved -> all drafts -> tick posts nothing.
    result = svc.tick(actor="test")
    assert result["posted"] is None
    assert len(publisher.posted) == 0
    assert all(c["status"] == "draft" for c in svc.list_cards())


def test_publish_ledger_is_append_only():
    svc, _ = _fresh_service()
    svc.create_card({"title": "Ledger test", "para1": "a", "para2": "b"})
    rows = svc.query_ledger()
    assert len(rows) >= 1
    row_id = rows[0]["id"]

    conn = svc.store._connect()
    try:
        raised_update = False
        try:
            conn.execute(
                "UPDATE publish_ledger SET actor = 'tamper' WHERE id = ?", (row_id,)
            )
            conn.commit()
        except Exception:
            raised_update = True
        assert raised_update, "ledger UPDATE must be blocked"

        raised_delete = False
        try:
            conn.execute("DELETE FROM publish_ledger WHERE id = ?", (row_id,))
            conn.commit()
        except Exception:
            raised_delete = True
        assert raised_delete, "ledger DELETE must be blocked"
    finally:
        conn.close()


def test_linkedin_publisher_returns_ok_false_until_wired():
    """The chokepoint must fail loudly (never fake a post) before it is wired."""
    svc, _ = _fresh_service()
    card = svc.create_card({"title": "LI test", "para1": "a", "para2": "b"})
    publisher = LinkedInPublisher()
    result = publisher.publish(card, card["image_path"])
    assert result.ok is False
    assert result.provider == "linkedin"
    assert result.error  # a clear, non-empty error


# ---------------------------------------------------------------------------
# Integration tests (spec section 9)
# ---------------------------------------------------------------------------

def test_integration_seed_approve_tick():
    svc, publisher = _fresh_service()
    svc.seed(actor="test")
    svc.update_schedule(
        {"cadence_days": 3, "start_date": _past_iso(), "next_due": _past_iso()},
        actor="test",
    )
    card = svc.list_cards()[0]
    svc.approve_card(card["id"], actor="founder")

    before = svc.get_schedule()["next_due"]
    result = svc.tick(actor="cron")

    posted = svc.get_card(card["id"])
    assert posted["status"] == "posted"
    assert result["posted"]["id"] == card["id"]

    # Ledger entry written for the post.
    posted_events = [e for e in svc.query_ledger() if e["event_type"] == "card_posted"]
    assert len(posted_events) == 1
    assert posted_events[0]["entity_id"] == card["id"]

    # next_due advanced by cadence.
    after = svc.get_schedule()["next_due"]
    assert datetime.fromisoformat(after) - datetime.fromisoformat(before) == timedelta(days=3)


def test_integration_tick_before_start_posts_nothing():
    svc, publisher = _fresh_service()
    svc.seed(actor="test")
    # start_date / next_due in the future -> the schedule clock has not opened.
    svc.update_schedule(
        {"start_date": _future_iso(), "next_due": _future_iso()}, actor="test"
    )
    card = svc.list_cards()[0]
    svc.approve_card(card["id"], actor="founder")  # approved, but not yet due

    result = svc.tick(actor="cron")
    assert result["posted"] is None
    assert result["reason"] == "not_due"
    assert len(publisher.posted) == 0
    assert svc.get_card(card["id"])["status"] == "approved"


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
