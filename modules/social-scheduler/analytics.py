"""
EVA Social-Scheduler — unified engagement analytics (Eva owns the data).

Per published post, we snapshot over time: platform, post_id, impressions,
likes, comments, clicks, retrieved_at — into the ONE local sqlite store
(``store.analytics``). No SaaS analytics DB.

Two metric sources, both behind seams so the sandbox/tests fire no network:
  * **X (Twitter)** — ``twitter_connector.get_tweet_metrics`` (X API v2,
    public + non-public metrics via the app Bearer token).
  * **LinkedIn** — reuses ``modules/linkedin-analytics`` (its ``AnalyticsClient``
    fetches per-post metrics; default is the offline stub until OAuth is wired
    on the host).

``AnalyticsSync.sync()`` walks ``post_history``, pulls current metrics for each
platform id, and upserts a snapshot. It's meant to run hourly during 8am–6pm ET
(see ``scheduler.in_analytics_window``).
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

import store

_CHANNELS_DIR = os.path.join(os.path.dirname(__file__), "..", "channels")
_LI_ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "..", "linkedin-analytics")


def _live_x_metrics(tweet_id: str, cfg: dict) -> dict:
    """Default X metric fetch via the channels twitter_connector."""
    p = os.path.abspath(_CHANNELS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    from twitter_connector import get_tweet_metrics
    return get_tweet_metrics(tweet_id, cfg)


def _build_li_client():
    """Default LinkedIn analytics client (offline stub unless host-wired)."""
    p = os.path.abspath(_LI_ANALYTICS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    from client import build_client
    return build_client()


class AnalyticsSync:
    """Pulls per-post metrics and upserts snapshots into the local store.

    Seams (all injectable for offline tests):
      * ``x_metrics(tweet_id, cfg) -> dict``  — X metric fetch.
      * ``li_client``                         — linkedin-analytics AnalyticsClient.
    """

    def __init__(self, *, db_path: str = store.DB_PATH, cfg: Optional[dict] = None,
                 x_metrics: Optional[Callable[[str, dict], dict]] = None,
                 li_client=None, author_urn: str = "",
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.cfg = cfg or {}
        self.author_urn = author_urn
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_SOCIAL_SCHEDULER_OFFLINE") == "1")
        self._x_metrics = x_metrics
        self._li_client = li_client
        store.init_db(self.db_path)

    def _x_fetch(self, tweet_id: str) -> dict:
        if self._x_metrics is not None:
            return self._x_metrics(tweet_id, self.cfg)
        if self.offline:
            return {"status": "skipped_offline"}
        return _live_x_metrics(tweet_id, self.cfg)

    def _li_metrics_map(self, window_days: int = 30) -> dict:
        """post_urn -> metrics dict, from the linkedin-analytics client."""
        client = self._li_client
        if client is None:
            if self.offline:
                return {}
            client = _build_li_client()
        try:
            result = client.fetch(self.author_urn, window_days)
        except Exception:
            return {}
        if not getattr(result, "ok", False):
            return {}
        out = {}
        for pm in result.posts:
            out[pm.post_urn] = {
                "impressions": pm.impressions,
                "likes": pm.reactions,
                "comments": pm.comments,
                "clicks": pm.clicks,
            }
        return out

    def sync(self, window_days: int = 30) -> dict:
        """Snapshot metrics for every post in history. Returns a summary."""
        posts = store.list_posts(path=self.db_path)
        li_map = self._li_metrics_map(window_days)
        synced, skipped = [], []

        for post in posts:
            x_id = post.get("x_tweet_id")
            if x_id:
                m = self._x_fetch(x_id)
                if m.get("status") == "ok":
                    store.record_metric(
                        platform="x", post_id=x_id,
                        impressions=m.get("impressions", 0),
                        likes=m.get("likes", 0),
                        comments=m.get("comments", 0),
                        clicks=m.get("clicks", 0),
                        path=self.db_path)
                    synced.append({"platform": "x", "post_id": x_id})
                else:
                    skipped.append({"platform": "x", "post_id": x_id,
                                    "reason": m.get("status") or m.get("error")})

            li_id = post.get("li_post_id")
            if li_id:
                m = li_map.get(li_id)
                if m:
                    store.record_metric(
                        platform="linkedin", post_id=li_id,
                        impressions=m["impressions"], likes=m["likes"],
                        comments=m["comments"], clicks=m["clicks"],
                        path=self.db_path)
                    synced.append({"platform": "linkedin", "post_id": li_id})
                else:
                    skipped.append({"platform": "linkedin", "post_id": li_id,
                                    "reason": "no metrics (offline/not wired)"})

        return {"ok": True, "synced": synced, "skipped": skipped,
                "synced_count": len(synced)}

    def report(self) -> dict:
        """Latest snapshot per (platform, post_id) — the /analytics payload."""
        latest = store.latest_metrics(path=self.db_path)
        totals = {"impressions": 0, "likes": 0, "comments": 0, "clicks": 0}
        for row in latest:
            for k in totals:
                totals[k] += int(row.get(k, 0) or 0)
        return {"posts": latest, "totals": totals, "count": len(latest)}


__all__ = ["AnalyticsSync"]
