"""
EVA Social-Scheduler — service layer (seed → submit → approve → publish →
LIKE + CTA → log → analytics).

Wires the pieces without duplicating anything:

  * the **queue** (local sqlite via ``store`` / ``queue``),
  * the existing **social-publish** approve-then-publish Slack gate (imported,
    behind the ``GateClient`` seam),
  * post-publish **cta** engagement (LIKE + CTA comment/reply),
  * **analytics** sync (X API v2 + linkedin-analytics into the unified store),
  * the **eva-state** ledger (``state_client``).

The per-post flow (spec):
  1. At/after a slot's ET time, submit the queued post to the Slack gate.
  2. On approval, the gate publishes to LinkedIn + X.
  3. Immediately LIKE + comment/reply the CTA on each platform.
  4. Log the published post + platform IDs to the store and eva-state.

Everything network-touching is injected (gate, engagement, state, clock) so the
whole service runs offline in tests and fires nothing real.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Protocol, runtime_checkable

import cta as cta_mod
import queue as queue_mod
import scheduler
import store
from analytics import AnalyticsSync
from state_client import StateLedgerClient, build_state_client

_SOCIAL_PUBLISH_DIR = os.path.join(os.path.dirname(__file__), "..", "social-publish")


def card_path(image: str) -> str:
    """Resolve a queue image basename to a full path via EVA_SOCIAL_CARD_DIR."""
    if not image:
        return ""
    if os.path.isabs(image):
        return image
    card_dir = os.environ.get("EVA_SOCIAL_CARD_DIR", "").strip()
    return os.path.join(card_dir, image) if card_dir else image


# ---------------------------------------------------------------------------
# Gate seam — wraps modules/social-publish (import, do not duplicate)
# ---------------------------------------------------------------------------

@runtime_checkable
class GateClient(Protocol):
    def submit(self, *, text: str, image_path: str, platforms: list[str]) -> dict: ...
    def is_approved(self, draft_id: str) -> dict: ...
    def approve(self, draft_id: str) -> dict: ...


class LiveGateClient:
    """Delegates to the social-publish gate + slack_client (real Slack + LI/X)."""

    def __init__(self) -> None:
        p = os.path.abspath(_SOCIAL_PUBLISH_DIR)
        if p not in sys.path:
            sys.path.insert(0, p)

    def submit(self, *, text: str, image_path: str, platforms: list[str]) -> dict:
        import gate  # noqa: PLC0415
        return gate.submit_for_approval(text, image_path=image_path, platforms=platforms)

    def is_approved(self, draft_id: str) -> dict:
        import slack_client  # noqa: PLC0415
        import store as sp_store  # noqa: PLC0415
        draft = sp_store.get_draft(draft_id)
        if not draft:
            return {"approved": False, "reason": "draft not found"}
        ts, channel = draft.get("slack_ts"), draft.get("slack_channel")
        if not ts or not channel:
            return {"approved": False, "reason": "no slack thread"}
        return slack_client.check_approval(channel, ts)

    def approve(self, draft_id: str) -> dict:
        import gate  # noqa: PLC0415
        return gate.approve(draft_id, actor="social-scheduler", via="scheduler")


def build_gate_client() -> GateClient:
    return LiveGateClient()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SocialSchedulerService:
    def __init__(self, *, db_path: str = store.DB_PATH,
                 state: Optional[StateLedgerClient] = None,
                 gate: Optional[GateClient] = None,
                 engagement: Optional[cta_mod.EngagementClient] = None,
                 cfg: Optional[dict] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_SOCIAL_SCHEDULER_OFFLINE") == "1")
        self.state = state or build_state_client(offline=self.offline)
        self.gate = gate or (None if self.offline else build_gate_client())
        self.engagement = engagement or cta_mod.build_engagement_client(offline=self.offline)
        self.cfg = cfg if cfg is not None else self._build_cfg()
        store.init_db(self.db_path)

    def _build_cfg(self) -> dict:
        """LinkedIn + X creds via social-publish credentials, plus X bearer."""
        cfg = {"linkedin": {}, "twitter": {}}
        try:
            p = os.path.abspath(_SOCIAL_PUBLISH_DIR)
            if p not in sys.path:
                sys.path.insert(0, p)
            import credentials  # noqa: PLC0415
            cfg = credentials.build_cfg()
        except Exception:
            pass
        # Bearer token for X analytics reads (not covered by the OAuth1 set).
        cfg.setdefault("twitter", {})
        cfg["twitter"].setdefault(
            "bearer_token", os.environ.get("X_BEARER_TOKEN", "").strip())
        return cfg

    # -- schedule views ------------------------------------------------------

    def schedule(self, now=None) -> dict:
        """The queue grouped by status + the fixed ET slot definition."""
        items = store.list_queue(path=self.db_path)
        by_status: dict[str, list] = {}
        for it in items:
            by_status.setdefault(it["status"], []).append(it)
        return {
            "timezone": "America/New_York",
            "slots": scheduler.SLOTS,
            "cta": scheduler.CTA_COMMENT,
            "now_et": scheduler.now_et(now).isoformat(),
            "counts": {k: len(v) for k, v in by_status.items()},
            "queue": items,
        }

    def seed(self, scheduled_date: str | None = None) -> dict:
        res = queue_mod.seed_day1(scheduled_date=scheduled_date, path=self.db_path)
        self.state.emit(event_type="queue_seeded",
                        summary=f"Social-scheduler seeded {len(res['added'])} day-1 posts",
                        entity_id=res["scheduled_date"], payload=res)
        return res

    # -- the run pass --------------------------------------------------------

    def run(self, now=None) -> dict:
        """One scheduler pass: submit due posts, publish approved ones, prune."""
        submitted = self._submit_due(now=now)
        published = self._publish_approved()
        pruned = queue_mod.prune(now=now, path=self.db_path)
        return {"ok": True, "submitted": submitted, "published": published,
                "pruned": pruned, "now_et": scheduler.now_et(now).isoformat()}

    def _submit_due(self, now=None) -> list[dict]:
        out = []
        for item in queue_mod.due_items(now=now, path=self.db_path):
            if self.gate is None:  # offline: no gate wired, cannot submit
                out.append({"queue_id": item["id"], "status": "no_gate_offline"})
                continue
            res = self.gate.submit(
                text=item["text"], image_path=card_path(item["image_path"]),
                platforms=item["platforms"])
            draft = res.get("draft") or {}
            draft_id = draft.get("id", "")
            if draft_id:
                store.update_queue_item(item["id"], {
                    "status": store.STATUS_SUBMITTED, "draft_id": draft_id},
                    path=self.db_path)
                self.state.emit(
                    event_type="post_submitted",
                    summary=f"Submitted for approval: {item['headline']}",
                    entity_id=item["id"],
                    payload={"draft_id": draft_id, "slot": item["slot"],
                             "scheduled_date": item["scheduled_date"]})
            out.append({"queue_id": item["id"], "draft_id": draft_id,
                        "slack": res.get("slack")})
        return out

    def _publish_approved(self) -> list[dict]:
        out = []
        if self.gate is None:
            return out
        for item in queue_mod.submitted_items(path=self.db_path):
            draft_id = item.get("draft_id")
            if not draft_id:
                continue
            verdict = self.gate.is_approved(draft_id)
            if not verdict.get("approved"):
                out.append({"queue_id": item["id"], "approved": False})
                continue
            pub = self.gate.approve(draft_id)
            outcome = self._after_publish(item, pub)
            out.append({"queue_id": item["id"], "approved": True, **outcome})
        return out

    def _after_publish(self, item: dict, pub: dict) -> dict:
        """Extract IDs, run LIKE + CTA, log to store + eva-state."""
        results = pub.get("results", {}) or {}
        li_post_id = (results.get("linkedin", {}) or {}).get("post_id", "")
        x_tweet_id = str((results.get("x", {}) or {}).get("tweet_id", "") or "")

        published_ok = pub.get("status") == "published" or bool(li_post_id or x_tweet_id)

        engage = {}
        if published_ok:
            engage = self.engagement.engage(
                li_post_id=li_post_id, x_tweet_id=x_tweet_id,
                cta_text=item.get("cta") or scheduler.CTA_COMMENT, cfg=self.cfg)

        record = store.record_post(
            queue_id=item["id"], headline=item["headline"],
            li_post_id=li_post_id, x_tweet_id=x_tweet_id,
            li_comment_id=cta_mod.extract_comment_id(engage),
            x_reply_id=cta_mod.extract_reply_id(engage),
            li_liked=cta_mod.liked_linkedin(engage),
            x_liked=cta_mod.liked_x(engage),
            results={"publish": results, "engagement": engage},
            path=self.db_path)

        new_status = store.STATUS_PUBLISHED if published_ok else store.STATUS_FAILED
        store.update_queue_item(item["id"], {"status": new_status}, path=self.db_path)

        self.state.emit(
            event_type="post_published" if published_ok else "post_failed",
            summary=(f"Published + CTA: {item['headline']}" if published_ok
                     else f"Publish failed: {item['headline']}"),
            entity_id=item["id"],
            payload={"li_post_id": li_post_id, "x_tweet_id": x_tweet_id,
                     "publish_status": pub.get("status"),
                     "post_history_id": record["id"]})
        return {"published": published_ok, "li_post_id": li_post_id,
                "x_tweet_id": x_tweet_id, "post_history_id": record["id"]}

    # -- analytics -----------------------------------------------------------

    def _syncer(self) -> AnalyticsSync:
        return AnalyticsSync(db_path=self.db_path, cfg=self.cfg, offline=self.offline)

    def sync_analytics(self, window_days: int = 30) -> dict:
        res = self._syncer().sync(window_days=window_days)
        self.state.emit(event_type="analytics_synced",
                        summary=f"Synced {res['synced_count']} post metric snapshots",
                        entity_id="social-scheduler", payload={"synced": res["synced_count"]})
        return res

    def analytics(self) -> dict:
        return self._syncer().report()


__all__ = ["SocialSchedulerService", "GateClient", "LiveGateClient",
           "build_gate_client", "card_path"]
