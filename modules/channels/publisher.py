"""
EVA Channels — publisher interface (the transport layer).

The publish workflow (approval gate + scheduling) is fully decoupled from the
transport, mirroring postcards' ``publisher.py`` and outreach's ``sender.py``.
The ``PublishResult`` shape is a superset of postcards' (``ok, provider,
post_url, error``) plus ``needs_manual_publish`` for Substack — so postcards
could later publish through these adapters by composition without breaking.

Implementations:
  * ``StubPublisher``  — offline, no network. In its default (real) mode it
    returns ``ok=False`` with a "not wired" error (a stub must never fake a
    post). Constructed with ``fake_success=True`` it returns ``ok=True`` with a
    synthetic ``post_url`` so tests can exercise the posted path.
  * ``RedditPublisher``   — shells out to ``reddit_post.py`` (the network
    chokepoint).
  * ``SubstackPublisher`` — shells out to ``substack_post.py`` (exports a
    markdown draft; always ``needs_manual_publish=True``).

Each concrete publisher targets one platform, so ``publish(item)`` needs no
platform argument; the service holds a ``{platform: Publisher}`` registry and
dispatches by ``item["platform"]``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger("eva.channels.publisher")

_REDDIT_SCRIPT = os.path.join(os.path.dirname(__file__), "reddit_post.py")
_SUBSTACK_SCRIPT = os.path.join(os.path.dirname(__file__), "substack_post.py")


@dataclass
class PublishResult:
    ok: bool
    provider: str
    post_url: str = ""
    error: str = ""
    needs_manual_publish: bool = False


class Publisher(Protocol):
    """Transport interface. Implementations must not raise on normal failure;
    they return a ``PublishResult`` with ``ok=False`` instead."""

    name: str

    def publish(self, item: dict) -> PublishResult: ...


class StubPublisher:
    """Offline publisher used in tests and for local render.

    Default (``fake_success=False``) is the honest "real" stub: it performs no
    network I/O and returns ``ok=False`` with a "not wired" error, so an unwired
    transport fails loudly. With ``fake_success=True`` it returns ``ok=True`` and
    a synthetic ``post_url`` so tests can exercise the posted path without a
    network."""

    def __init__(
        self,
        platform: str = "stub",
        fake_success: bool = False,
        sink: Optional[list[dict]] = None,
    ):
        self.name = platform
        self.fake_success = fake_success
        # Optional in-memory sink so tests/UI can inspect what "would" be posted.
        self.posted: list[dict] = sink if sink is not None else []

    def publish(self, item: dict) -> PublishResult:
        self.posted.append({"item_id": item.get("id"), "platform": self.name})
        if self.fake_success:
            logger.info(
                "[stub-publisher] FAKE-SUCCESS post item=%s platform=%s",
                item.get("id"), self.name,
            )
            return PublishResult(
                ok=True,
                provider=self.name,
                post_url=f"stub://{self.name}/{item.get('id', 'unknown')}",
            )
        logger.info(
            "[stub-publisher] not wired — would post item=%s platform=%s",
            item.get("id"), self.name,
        )
        return PublishResult(
            ok=False,
            provider=self.name,
            error=f"{self.name} transport not wired (stub)",
        )


def _run_chokepoint(script: str, provider: str, request: dict) -> PublishResult:
    """Invoke a chokepoint script with a JSON request on stdin and parse the
    JSON result from stdout — the shared spirit of outreach's ``gmail_send.py``.
    """
    try:
        proc = subprocess.run(
            [sys.executable, script],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return PublishResult(
            ok=False, provider=provider,
            error=f"failed to invoke {os.path.basename(script)}: {exc}",
        )

    if proc.returncode != 0 and not proc.stdout.strip():
        return PublishResult(
            ok=False, provider=provider,
            error=(proc.stderr.strip()
                   or f"{os.path.basename(script)} exited {proc.returncode}"),
        )
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return PublishResult(
            ok=False, provider=provider,
            error=f"invalid JSON from {os.path.basename(script)}: {proc.stdout!r}",
        )
    return PublishResult(
        ok=bool(data.get("ok")),
        provider=data.get("provider", provider),
        post_url=data.get("post_url", ""),
        error=data.get("error", ""),
        needs_manual_publish=bool(data.get("needs_manual_publish", False)),
    )


class RedditPublisher:
    """Shells out to ``reddit_post.py`` (the Reddit network chokepoint). Returns
    ``ok=False, error="Reddit credentials not set"`` until the host wires it."""

    name = "reddit"

    def __init__(self, config: Optional[dict] = None, script_path: str = _REDDIT_SCRIPT):
        self.config = config or {}
        self.script_path = script_path

    def publish(self, item: dict) -> PublishResult:
        cfg = self.config
        payload = _item_payload(item)
        request = {
            "title": item.get("title", ""),
            "body": item.get("body", ""),
            "subreddit": payload.get("subreddit") or cfg.get("subreddit", ""),
            "kind": payload.get("kind") or cfg.get("kind", "self"),
            "client_id_env": cfg.get("client_id_env", "REDDIT_CLIENT_ID"),
            "client_secret_env": cfg.get("client_secret_env", "REDDIT_CLIENT_SECRET"),
            "username_env": cfg.get("username_env", "REDDIT_USERNAME"),
            "password_env": cfg.get("password_env", "REDDIT_PASSWORD"),
            "user_agent": cfg.get("user_agent", "Eva/0.1 by u/eva"),
        }
        return _run_chokepoint(self.script_path, self.name, request)


class SubstackPublisher:
    """Shells out to ``substack_post.py`` (exports a markdown draft). Always
    returns ``ok=False, needs_manual_publish=True`` — Substack has no public
    posting API, so v1 never fakes success."""

    name = "substack"

    def __init__(self, config: Optional[dict] = None, script_path: str = _SUBSTACK_SCRIPT):
        self.config = config or {}
        self.script_path = script_path

    def publish(self, item: dict) -> PublishResult:
        cfg = self.config
        request = {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "body": item.get("body", ""),
            "publication_url": cfg.get("publication_url", ""),
            "session_env": cfg.get("session_env", "SUBSTACK_SESSION_COOKIE"),
        }
        return _run_chokepoint(self.script_path, self.name, request)


def _item_payload(item: dict) -> dict:
    """Parse the per-item ``payload_json`` blob (platform-specific extras)."""
    raw = item.get("payload_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def build_publisher(platform: str, config: Optional[dict] = None) -> Publisher:
    """Factory: the real transport for a platform. ``EVA_CHANNELS_PUBLISHER=stub``
    forces the (honest, not-wired) stub for every platform."""
    if os.environ.get("EVA_CHANNELS_PUBLISHER", "").lower() == "stub":
        return StubPublisher(platform=platform)
    if platform == "reddit":
        return RedditPublisher(config=config)
    if platform == "substack":
        return SubstackPublisher(config=config)
    return StubPublisher(platform=platform)
