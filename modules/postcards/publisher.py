"""
EVA Postcards — publisher interface.

The publish workflow (approval gate + scheduling) is fully decoupled from the
transport, mirroring outreach's ``sender.py``. v1 ships a ``StubPublisher`` that
renders the PNG to disk and logs — it never touches the network. A
``LinkedInPublisher`` shells out to ``linkedin_post.py`` (the single network
chokepoint); until that chokepoint is wired on the Eva host it returns
``ok=False`` with a clear error and never silently fakes a post.

Select the implementation with the ``EVA_POSTCARDS_PUBLISHER`` env var
(``stub`` | ``linkedin``) or by passing an explicit instance into the service.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("eva.postcards.publisher")

# Composed once and reused; the Eva host can override at wiring time.
_DEFAULT_POST_TEXT_TEMPLATE = "{para1}\n\n{para2}"
_ACCESS_TOKEN_ENV = "LINKEDIN_ACCESS_TOKEN"
_LINKEDIN_SCRIPT = os.path.join(os.path.dirname(__file__), "linkedin_post.py")


@dataclass
class PublishResult:
    ok: bool
    provider: str
    post_url: str = ""
    error: str = ""


def build_post_text(card: dict) -> str:
    return _DEFAULT_POST_TEXT_TEMPLATE.format(
        para1=card.get("para1", ""), para2=card.get("para2", "")
    ).strip()


class Publisher(Protocol):
    """Transport interface. Implementations must not raise on normal failure;
    they return a ``PublishResult`` with ``ok=False`` instead."""

    name: str

    def publish(self, card: dict, image_path: str) -> PublishResult: ...


class StubPublisher:
    """v1 default: assumes the PNG is already rendered to disk, logs, and
    returns success. No network I/O."""

    name = "stub"

    def __init__(self, sink: list[dict] | None = None):
        # Optional in-memory sink so tests/UI can inspect what "would" be posted.
        self.posted: list[dict] = sink if sink is not None else []

    def publish(self, card: dict, image_path: str) -> PublishResult:
        self.posted.append({"card_id": card.get("id"), "image_path": image_path})
        logger.info(
            "[stub-publisher] would post card=%s title=%r image=%s",
            card.get("id"),
            card.get("title"),
            image_path,
        )
        return PublishResult(ok=True, provider=self.name, post_url="")


class LinkedInPublisher:
    """Shells out to ``linkedin_post.py`` (the network chokepoint), passing a
    JSON request on stdin and reading a JSON result from stdout — the same
    spirit as outreach's ``gmail_send.py`` hook. Returns ``ok=False`` with a
    clear error until ``linkedin_post.py::_post_via_linkedin_api`` is wired."""

    name = "linkedin"

    def __init__(
        self,
        script_path: str = _LINKEDIN_SCRIPT,
        access_token_env: str = _ACCESS_TOKEN_ENV,
    ):
        self.script_path = script_path
        self.access_token_env = access_token_env

    def publish(self, card: dict, image_path: str) -> PublishResult:
        request = {
            "text": build_post_text(card),
            "image_path": image_path,
            "access_token_env": self.access_token_env,
        }
        try:
            proc = subprocess.run(
                [sys.executable, self.script_path],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return PublishResult(
                ok=False,
                provider=self.name,
                error=f"failed to invoke linkedin_post.py: {exc}",
            )

        if proc.returncode != 0 and not proc.stdout.strip():
            return PublishResult(
                ok=False,
                provider=self.name,
                error=(proc.stderr.strip() or f"linkedin_post.py exited {proc.returncode}"),
            )
        try:
            data = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return PublishResult(
                ok=False,
                provider=self.name,
                error=f"invalid JSON from linkedin_post.py: {proc.stdout!r}",
            )
        return PublishResult(
            ok=bool(data.get("ok")),
            provider=data.get("provider", self.name),
            post_url=data.get("post_url", ""),
            error=data.get("error", ""),
        )


def build_publisher(name: str | None = None) -> Publisher:
    """Factory. Defaults to the stub unless EVA_POSTCARDS_PUBLISHER=linkedin."""
    choice = (name or os.environ.get("EVA_POSTCARDS_PUBLISHER", "stub")).lower()
    if choice == "linkedin":
        return LinkedInPublisher()
    return StubPublisher()
