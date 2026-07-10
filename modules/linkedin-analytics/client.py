"""
EVA LinkedIn Analytics — transport interface.

The analytics read workflow is fully decoupled from the transport, mirroring
postcards' ``publisher.py`` and outreach's ``sender.py``. Two implementations
sit behind the ``AnalyticsClient`` Protocol:

  * ``StubAnalyticsClient`` — offline, returns ``ok=False`` with a clear
    "not wired" error and makes NO network call. This is the default used in
    tests and until the host wires OAuth.
  * ``LinkedInAnalyticsClient`` — shells out to ``linkedin_analytics.py`` (the
    single network chokepoint) over a JSON stdin/stdout contract. Until the
    chokepoint's ``_fetch_via_linkedin_api`` is implemented on the Eva host it
    also returns ``ok=False`` with a clear error.

Stubs never fake success. Tests that need to exercise the upsert path inject a
``FakeSuccessAnalyticsClient`` with deterministic sample data — a test double,
not a production transport.

Select the implementation with the ``EVA_LINKEDIN_ANALYTICS_CLIENT`` env var
(``stub`` | ``linkedin``) or by passing an explicit instance into the service.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Protocol

from models import DEFAULT_ACCESS_TOKEN_ENV

logger = logging.getLogger("eva.linkedin_analytics.client")

_LINKEDIN_SCRIPT = os.path.join(os.path.dirname(__file__), "linkedin_analytics.py")

_NOT_WIRED_ERROR = (
    "LinkedIn OAuth/API not wired on Eva host — set LINKEDIN_ACCESS_TOKEN + "
    "author_urn and implement linkedin_analytics.py::_fetch_via_linkedin_api"
)


@dataclass
class PostMetrics:
    """Normalized per-post metrics returned by a fetch.

    ``engagement_rate`` may be None on input — the service computes it
    canonically as (reactions+comments+shares)/impressions so the stored value
    is always consistent regardless of what a transport reports.
    """

    post_urn: str
    share_urn: str = ""
    author_urn: str = ""
    posted_at: str = ""
    text: str = ""
    post_url: str = ""
    impressions: int = 0
    unique_impressions: int = 0
    clicks: int = 0
    reactions: int = 0
    comments: int = 0
    shares: int = 0
    engagement_rate: float | None = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "PostMetrics":
        return cls(
            post_urn=d.get("post_urn", ""),
            share_urn=d.get("share_urn", ""),
            author_urn=d.get("author_urn", ""),
            posted_at=d.get("posted_at", ""),
            text=d.get("text", ""),
            post_url=d.get("post_url", ""),
            impressions=int(d.get("impressions", 0) or 0),
            unique_impressions=int(d.get("unique_impressions", 0) or 0),
            clicks=int(d.get("clicks", 0) or 0),
            reactions=int(d.get("reactions", 0) or 0),
            comments=int(d.get("comments", 0) or 0),
            shares=int(d.get("shares", 0) or 0),
            engagement_rate=d.get("engagement_rate"),
            raw=d.get("raw", {}) or {},
        )


@dataclass
class FetchResult:
    ok: bool
    provider: str
    posts: List[PostMetrics] = field(default_factory=list)
    error: str = ""


class AnalyticsClient(Protocol):
    """Transport interface. Implementations must not raise on normal failure;
    they return a ``FetchResult`` with ``ok=False`` instead."""

    name: str

    def fetch(self, author_urn: str, window_days: int) -> FetchResult: ...


class StubAnalyticsClient:
    """Offline default. Returns ok=False with the "not wired" error and makes
    NO network call. Never fakes success."""

    name = "stub"

    def fetch(self, author_urn: str, window_days: int) -> FetchResult:
        logger.info(
            "[stub-analytics] fetch requested author=%r window_days=%s — "
            "transport not wired, returning ok=False",
            author_urn,
            window_days,
        )
        return FetchResult(ok=False, provider=self.name, posts=[],
                           error=_NOT_WIRED_ERROR)


class LinkedInAnalyticsClient:
    """Shells out to ``linkedin_analytics.py`` (the network chokepoint), passing
    a JSON request on stdin and reading a JSON result from stdout — the same
    spirit as postcards' ``LinkedInPublisher``. Returns ``ok=False`` with a
    clear error until ``linkedin_analytics.py::_fetch_via_linkedin_api`` is
    wired with a valid token."""

    name = "linkedin"

    def __init__(
        self,
        script_path: str = _LINKEDIN_SCRIPT,
        access_token_env: str = DEFAULT_ACCESS_TOKEN_ENV,
    ):
        self.script_path = script_path
        self.access_token_env = access_token_env

    def fetch(self, author_urn: str, window_days: int) -> FetchResult:
        request = {
            "author_urn": author_urn,
            "access_token_env": self.access_token_env,
            "window_days": window_days,
        }
        try:
            proc = subprocess.run(
                [sys.executable, self.script_path],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return FetchResult(
                ok=False,
                provider=self.name,
                error=f"failed to invoke linkedin_analytics.py: {exc}",
            )

        if proc.returncode != 0 and not proc.stdout.strip():
            return FetchResult(
                ok=False,
                provider=self.name,
                error=(proc.stderr.strip()
                       or f"linkedin_analytics.py exited {proc.returncode}"),
            )
        try:
            data = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return FetchResult(
                ok=False,
                provider=self.name,
                error=f"invalid JSON from linkedin_analytics.py: {proc.stdout!r}",
            )
        posts = [PostMetrics.from_dict(p) for p in data.get("posts", []) or []]
        return FetchResult(
            ok=bool(data.get("ok")),
            provider=data.get("provider", self.name),
            posts=posts,
            error=data.get("error", ""),
        )


def build_client(name: str | None = None) -> AnalyticsClient:
    """Factory. Defaults to the stub unless EVA_LINKEDIN_ANALYTICS_CLIENT=linkedin."""
    choice = (name or os.environ.get("EVA_LINKEDIN_ANALYTICS_CLIENT", "stub")).lower()
    if choice == "linkedin":
        return LinkedInAnalyticsClient()
    return StubAnalyticsClient()
