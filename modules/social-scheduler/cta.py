"""
EVA Social-Scheduler — post-publish engagement (LIKE + CTA comment).

Immediately after a post is published (via the social-publish gate), Eva:
  1. LIKEs the post on each platform, then
  2. Posts the CTA as a comment/reply:
     ``DM or comment "Eva-acquisition" to try it for free``
     (LinkedIn: comment on our own UGC post. X: reply to our own tweet.)

The transport is the *existing* channels connectors — no re-implementation:
  * LinkedIn: ``linkedin_connector.like_post`` + ``comment_on_post``
  * X:        ``twitter_connector.like_tweet`` + ``reply_tweet``

Everything sits behind an ``EngagementClient`` Protocol so tests inject a fake
and NOTHING real is ever liked/commented offline. ``build_engagement_client``
returns the no-op client in offline mode (the sandbox default) and the live
client on the Mac.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Protocol, runtime_checkable

_CHANNELS_DIR = os.path.join(os.path.dirname(__file__), "..", "channels")


def _ensure_channels_on_path() -> None:
    p = os.path.abspath(_CHANNELS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


@runtime_checkable
class EngagementClient(Protocol):
    def engage(self, *, li_post_id: str, x_tweet_id: str, cta_text: str,
               cfg: dict) -> dict: ...


class NoopEngagementClient:
    """Offline default — records the intended engagement, fires nothing."""

    name = "noop"

    def engage(self, *, li_post_id: str, x_tweet_id: str, cta_text: str,
               cfg: dict) -> dict:
        return {
            "linkedin": {"like": {"status": "skipped_offline"},
                         "comment": {"status": "skipped_offline"}},
            "x": {"like": {"status": "skipped_offline"},
                  "reply": {"status": "skipped_offline"}},
        }


class LiveEngagementClient:
    """Live engagement via the channels connectors (LinkedIn + X)."""

    name = "live"

    def engage(self, *, li_post_id: str, x_tweet_id: str, cta_text: str,
               cfg: dict) -> dict:
        _ensure_channels_on_path()
        result: dict = {"linkedin": {}, "x": {}}

        if li_post_id:
            try:
                from linkedin_connector import comment_on_post, like_post
                result["linkedin"]["like"] = like_post(li_post_id, cfg)
                result["linkedin"]["comment"] = comment_on_post(li_post_id, cta_text, cfg)
            except Exception as exc:  # missing dep / unexpected
                result["linkedin"]["error"] = f"linkedin engagement failed: {exc}"
        else:
            result["linkedin"] = {"status": "no_post_id"}

        if x_tweet_id:
            try:
                from twitter_connector import like_tweet, reply_tweet
                result["x"]["like"] = like_tweet(x_tweet_id, cfg)
                result["x"]["reply"] = reply_tweet(cta_text, x_tweet_id, cfg)
            except Exception as exc:
                result["x"]["error"] = f"x engagement failed: {exc}"
        else:
            result["x"] = {"status": "no_tweet_id"}

        return result


def build_engagement_client(offline: Optional[bool] = None) -> EngagementClient:
    use_noop = offline
    if use_noop is None:
        use_noop = os.environ.get("EVA_SOCIAL_SCHEDULER_OFFLINE") == "1"
    return NoopEngagementClient() if use_noop else LiveEngagementClient()


def extract_comment_id(engage_result: dict) -> str:
    return ((engage_result.get("linkedin", {}) or {}).get("comment", {}) or {}).get("comment_id", "")


def extract_reply_id(engage_result: dict) -> str:
    reply = ((engage_result.get("x", {}) or {}).get("reply", {}) or {})
    return str(reply.get("tweet_id", "") or "")


def liked_linkedin(engage_result: dict) -> bool:
    return ((engage_result.get("linkedin", {}) or {}).get("like", {}) or {}).get("status") == "liked"


def liked_x(engage_result: dict) -> bool:
    return ((engage_result.get("x", {}) or {}).get("like", {}) or {}).get("status") == "liked"


__all__ = [
    "EngagementClient", "NoopEngagementClient", "LiveEngagementClient",
    "build_engagement_client", "extract_comment_id", "extract_reply_id",
    "liked_linkedin", "liked_x",
]
