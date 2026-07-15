"""
EVA Social-Scheduler — offline test suite (fake gate/engagement, stub ledger,
zero network). Nothing real is EVER posted / liked / commented: the gate is a
deterministic fake, the engagement client is a fake, Slack is never touched,
and the state client is a stub.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module runs:

  python modules/social-scheduler/test_social_scheduler.py
  (or)  cd modules/social-scheduler && python test_social_scheduler.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EVA_SOCIAL_SCHEDULER_OFFLINE"] = "1"
os.environ.pop("SLACK_BOT_TOKEN", None)  # ensure Slack never fires

import cta as cta_mod
import queue as queue_mod
import scheduler
import store
from analytics import AnalyticsSync
from service import SocialSchedulerService, card_path
from state_client import StubStateLedgerClient

ET = scheduler.ET


# ---------------------------------------------------------------------------
# Fakes (test doubles — never a real transport)
# ---------------------------------------------------------------------------

class FakeGate:
    """Deterministic gate double. Records submissions; approves on demand."""

    def __init__(self, auto_approve=True, li_id="urn:li:ugcPost:111",
                 x_id="9001", unique=False):
        self.auto_approve = auto_approve
        self.li_id = li_id
        self.x_id = x_id
        self.unique = unique
        self.submitted = []
        self._drafts = {}
        self._n = 0
        self._ac = 0

    def submit(self, *, text, image_path, platforms):
        self._n += 1
        draft_id = f"draft-{self._n}"
        self._drafts[draft_id] = {"text": text, "image_path": image_path,
                                  "platforms": platforms}
        self.submitted.append(draft_id)
        return {"draft": {"id": draft_id}, "slack": {"ok": True, "ts": "1.1"}}

    def is_approved(self, draft_id):
        return {"approved": self.auto_approve, "via": "reaction"}

    def approve(self, draft_id):
        self._ac += 1
        suffix = f"-{self._ac}" if self.unique else ""
        return {"ok": True, "status": "published",
                "results": {"linkedin": {"status": "posted", "post_id": self.li_id + suffix},
                            "x": {"status": "posted", "tweet_id": self.x_id + suffix}}}


class FakeEngagement:
    """Engagement double — reports a successful like + comment/reply."""

    def __init__(self):
        self.calls = []

    def engage(self, *, li_post_id, x_tweet_id, cta_text, cfg):
        self.calls.append({"li": li_post_id, "x": x_tweet_id, "cta": cta_text})
        return {
            "linkedin": {"like": {"status": "liked"},
                         "comment": {"status": "commented", "comment_id": "c-1"}},
            "x": {"like": {"status": "liked"},
                  "reply": {"status": "posted", "tweet_id": "r-1"}},
        }


def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="social_sched_test_", suffix=".db")
    os.close(fd)
    os.unlink(path)
    store.init_db(path)
    return path


def _svc(db, gate=None, engagement=None, state=None):
    return SocialSchedulerService(
        db_path=db, state=state or StubStateLedgerClient(),
        gate=gate or FakeGate(), engagement=engagement or FakeEngagement(),
        cfg={"linkedin": {}, "twitter": {}}, offline=True)


# past/future ET datetimes so slot-due logic is deterministic
_PAST = datetime(2020, 1, 1, 12, 0, tzinfo=ET)
_FUTURE = datetime(2999, 1, 1, 12, 0, tzinfo=ET)


# ---------------------------------------------------------------------------
# scheduler — ET slot math
# ---------------------------------------------------------------------------

def test_five_slots_et():
    assert scheduler.SLOTS == ["08:00", "11:00", "14:00", "15:00", "17:00"]


def test_slot_due_uses_new_york_tz():
    # 09:00 ET on a fixed date is due when "now" is noon ET that day.
    now = datetime(2026, 7, 15, 12, 0, tzinfo=ET)
    assert scheduler.is_slot_due("2026-07-15", "08:00", now=now) is True
    assert scheduler.is_slot_due("2026-07-15", "17:00", now=now) is False


def test_now_et_converts_from_other_tz():
    # A naive/other-tz input is normalised to America/New_York.
    from zoneinfo import ZoneInfo
    la = datetime(2026, 7, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert scheduler.now_et(la).hour == 12  # LA 09:00 == ET 12:00 in summer


def test_analytics_window():
    assert scheduler.in_analytics_window(datetime(2026, 7, 15, 9, tzinfo=ET)) is True
    assert scheduler.in_analytics_window(datetime(2026, 7, 15, 19, tzinfo=ET)) is False


# ---------------------------------------------------------------------------
# store / queue — dedupe + rolling window
# ---------------------------------------------------------------------------

def test_seed_day1_five_posts():
    db = _new_db()
    res = queue_mod.seed_day1(scheduled_date="2026-07-15", path=db)
    assert len(res["added"]) == 5
    assert len(store.list_queue(path=db)) == 5


def test_seed_is_idempotent_by_headline():
    db = _new_db()
    queue_mod.seed_day1(scheduled_date="2026-07-15", path=db)
    again = queue_mod.seed_day1(scheduled_date="2026-07-16", path=db)
    assert len(again["added"]) == 0
    assert len(again["skipped_duplicates"]) == 5
    assert len(store.list_queue(path=db)) == 5  # no repeat headlines


def test_headline_hash_stable():
    assert store.headline_hash("Hello World") == store.headline_hash("hello world")


def test_card_one_excluded_from_seed():
    db = _new_db()
    queue_mod.seed_day1(scheduled_date="2026-07-15", path=db)
    imgs = {it["image_path"] for it in store.list_queue(path=db)}
    assert "eva_linkedin_today.png" not in imgs  # card 1 already posted
    assert "eva_pe_card.png" in imgs


def test_prune_drops_stale_queued():
    db = _new_db()
    queue_mod.seed_day1(scheduled_date="2000-01-01", path=db)
    pruned = queue_mod.prune(window_days=30, now=_FUTURE, path=db)
    assert pruned == 5
    assert store.list_queue(path=db) == []


def test_due_items_respects_slot_time():
    db = _new_db()
    queue_mod.seed_day1(scheduled_date="2026-07-15", path=db)
    assert queue_mod.due_items(now=_PAST, path=db) == []       # before any slot
    assert len(queue_mod.due_items(now=_FUTURE, path=db)) == 5  # after all slots


# ---------------------------------------------------------------------------
# service.run — submit → approve → publish → CTA → log
# ---------------------------------------------------------------------------

def test_run_submits_due_posts():
    db = _new_db()
    gate = FakeGate(auto_approve=False)
    svc = _svc(db, gate=gate)
    svc.seed(scheduled_date="2026-07-15")
    res = svc.run(now=_FUTURE)
    assert len(res["submitted"]) == 5
    assert len(gate.submitted) == 5
    assert len(store.list_queue(status=store.STATUS_SUBMITTED, path=db)) == 5
    # not approved yet → nothing published
    assert all(not p["approved"] for p in res["published"])


def test_run_full_flow_publishes_and_engages():
    db = _new_db()
    gate = FakeGate(auto_approve=True)
    eng = FakeEngagement()
    state = StubStateLedgerClient()
    svc = _svc(db, gate=gate, engagement=eng, state=state)
    svc.seed(scheduled_date="2026-07-15")
    # A single pass submits the due posts AND (since they auto-approve)
    # publishes + runs the CTA in the same run.
    res = svc.run(now=_FUTURE)
    published = [p for p in res["published"] if p["approved"]]
    assert len(published) == 5
    assert len(eng.calls) == 5              # CTA ran for each
    assert len(store.list_posts(path=db)) == 5
    assert len(store.list_queue(status=store.STATUS_PUBLISHED, path=db)) == 5
    assert any(e["event_type"] == "post_published" for e in state.events)


def test_publish_records_platform_ids_and_cta():
    db = _new_db()
    svc = _svc(db, gate=FakeGate(li_id="urn:li:ugcPost:777", x_id="42"))
    svc.seed(scheduled_date="2026-07-15")
    svc.run(now=_FUTURE)
    svc.run(now=_FUTURE)
    post = store.list_posts(path=db)[0]
    assert post["li_post_id"] == "urn:li:ugcPost:777"
    assert post["x_tweet_id"] == "42"
    assert post["li_comment_id"] == "c-1"
    assert post["x_reply_id"] == "r-1"
    assert post["li_liked"] == 1 and post["x_liked"] == 1


def test_not_approved_stays_submitted():
    db = _new_db()
    svc = _svc(db, gate=FakeGate(auto_approve=False))
    svc.seed(scheduled_date="2026-07-15")
    svc.run(now=_FUTURE)
    svc.run(now=_FUTURE)
    assert len(store.list_queue(status=store.STATUS_SUBMITTED, path=db)) == 5
    assert store.list_posts(path=db) == []


def test_cta_text_is_the_spec_string():
    assert scheduler.CTA_COMMENT == 'DM or comment "Eva-acquisition" to try it for free'


def test_schedule_view_groups_by_status():
    db = _new_db()
    svc = _svc(db)
    svc.seed(scheduled_date="2026-07-15")
    view = svc.schedule(now=_PAST)
    assert view["timezone"] == "America/New_York"
    assert view["slots"] == scheduler.SLOTS
    assert view["counts"].get("queued") == 5


# ---------------------------------------------------------------------------
# analytics — unified local store, offline-safe seams
# ---------------------------------------------------------------------------

def test_analytics_sync_with_fake_x_metrics():
    db = _new_db()
    svc = _svc(db, gate=FakeGate(x_id="55", unique=True))
    svc.seed(scheduled_date="2026-07-15")
    svc.run(now=_FUTURE)  # submit + publish; 5 distinct x_tweet_ids

    def fake_x(tweet_id, cfg):
        return {"status": "ok", "impressions": 1000, "likes": 10,
                "comments": 2, "clicks": 5}

    syncer = AnalyticsSync(db_path=db, cfg={"twitter": {}}, x_metrics=fake_x,
                           li_client=None, offline=True)
    res = syncer.sync()
    assert res["synced_count"] >= 5  # one X snapshot per published post
    report = syncer.report()
    assert report["totals"]["impressions"] == 5000  # 5 posts × 1000
    assert report["totals"]["likes"] == 50


def test_analytics_snapshot_is_idempotent_per_timestamp():
    db = _new_db()
    store.record_metric(platform="x", post_id="1", impressions=10, likes=1,
                        retrieved_at="2026-07-15T10:00:00+00:00", path=db)
    store.record_metric(platform="x", post_id="1", impressions=20, likes=2,
                        retrieved_at="2026-07-15T10:00:00+00:00", path=db)
    rows = store.list_metrics(platform="x", post_id="1", path=db)
    assert len(rows) == 1            # upserted, not duplicated
    assert rows[0]["impressions"] == 20


def test_analytics_offline_x_is_skipped_not_faked():
    db = _new_db()
    svc = _svc(db, gate=FakeGate())
    svc.seed(scheduled_date="2026-07-15")
    svc.run(now=_FUTURE)
    svc.run(now=_FUTURE)
    # offline syncer with no injected fetch → X returns skipped_offline, LI empty
    res = AnalyticsSync(db_path=db, offline=True).sync()
    assert res["synced_count"] == 0
    assert all(s["reason"] in ("skipped_offline", "no metrics (offline/not wired)")
               for s in res["skipped"])


def test_offline_service_without_gate_does_not_publish():
    db = _new_db()
    # No injected gate + offline → gate is None; run must not crash or publish.
    svc = SocialSchedulerService(db_path=db, state=StubStateLedgerClient(),
                                 engagement=FakeEngagement(),
                                 cfg={"linkedin": {}, "twitter": {}}, offline=True)
    assert svc.gate is None
    svc.seed(scheduled_date="2026-07-15")
    res = svc.run(now=_FUTURE)
    assert all(s["status"] == "no_gate_offline" for s in res["submitted"])
    assert store.list_posts(path=db) == []


# ---------------------------------------------------------------------------
# cta / helpers
# ---------------------------------------------------------------------------

def test_card_path_abs_passthrough_and_join():
    assert card_path("") == ""
    assert card_path("/abs/x.png") == "/abs/x.png"
    os.environ["EVA_SOCIAL_CARD_DIR"] = "/cards"
    try:
        assert card_path("a.png") == "/cards/a.png"
    finally:
        os.environ.pop("EVA_SOCIAL_CARD_DIR", None)


def test_noop_engagement_fires_nothing():
    noop = cta_mod.NoopEngagementClient()
    r = noop.engage(li_post_id="x", x_tweet_id="y", cta_text="z", cfg={})
    assert r["linkedin"]["like"]["status"] == "skipped_offline"
    assert r["x"]["reply"]["status"] == "skipped_offline"


def test_cta_extract_helpers():
    r = {"linkedin": {"like": {"status": "liked"},
                      "comment": {"status": "commented", "comment_id": "c9"}},
         "x": {"like": {"status": "liked"}, "reply": {"tweet_id": "t9"}}}
    assert cta_mod.extract_comment_id(r) == "c9"
    assert cta_mod.extract_reply_id(r) == "t9"
    assert cta_mod.liked_linkedin(r) is True
    assert cta_mod.liked_x(r) is True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {t.__name__}")
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
