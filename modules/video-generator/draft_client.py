"""
EVA Video Generator — content-engine draft-pull client (behind a Protocol).

Lets a video be created from an existing content-engine draft
(``GET http://localhost:8767/drafts/{id}``) instead of a hand-typed script. The
fetch sits behind a ``DraftClient`` Protocol with an offline ``StubDraftClient``
for tests and an ``HttpDraftClient`` real impl. Same honest-failure style as
``state_client.py``: an unreachable content-engine returns ``{"ok": False}`` with
a clear error — it never fabricates a draft.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

CONTENT_ENGINE_URL = os.environ.get("CONTENT_ENGINE_URL", "http://localhost:8767")


@runtime_checkable
class DraftClient(Protocol):
    def fetch_draft(self, draft_id: str) -> dict:
        """Return {ok, draft_id, script_text, title, ...} or {ok: False, error}."""
        ...


def _to_result(draft_id: str, draft: dict) -> dict:
    script = (draft.get("draft_text") or "").strip()
    hook = (draft.get("hook") or "").strip()
    # content-engine drafts have no title; derive a short one from hook/text.
    title = hook or (script[:60] + ("…" if len(script) > 60 else "")) or f"Draft {draft_id[:8]}"
    return {
        "ok": True,
        "draft_id": draft_id,
        "title": title,
        "script_text": script,
        "hook": hook,
        "platform": draft.get("platform", ""),
    }


class StubDraftClient:
    """Offline draft source — serves pre-seeded drafts from a dict, no network."""

    def __init__(self, drafts: Optional[dict] = None) -> None:
        self.drafts = drafts or {}

    def add(self, draft_id: str, draft_text: str, hook: str = "") -> None:
        self.drafts[draft_id] = {"draft_text": draft_text, "hook": hook}

    def fetch_draft(self, draft_id: str) -> dict:
        draft = self.drafts.get(draft_id)
        if draft is None:
            return {"ok": False, "error": f"draft not found: {draft_id}"}
        return _to_result(draft_id, draft)


class HttpDraftClient:
    """Live draft source — GETs content-engine's /drafts/{id} endpoint."""

    def __init__(self, base_url: str = CONTENT_ENGINE_URL, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_draft(self, draft_id: str) -> dict:
        url = f"{self.base_url}/drafts/{draft_id}"
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if not (200 <= resp.status_code < 300):
                    return {"ok": False, "error": f"content-engine {resp.status_code}"}
                return _to_result(draft_id, resp.json())
        except ImportError:
            return self._fetch_urllib(url, draft_id)
        except Exception as exc:  # network/content-engine down — honest failure
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _fetch_urllib(self, url: str, draft_id: str) -> dict:
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                if not (200 <= resp.status < 300):
                    return {"ok": False, "error": f"content-engine {resp.status}"}
                return _to_result(draft_id, json.loads(resp.read().decode()))
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_draft_client(offline: Optional[bool] = None) -> DraftClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_VIDEO_OFFLINE") == "1"
    return StubDraftClient() if use_stub else HttpDraftClient()


__all__ = [
    "DraftClient",
    "StubDraftClient",
    "HttpDraftClient",
    "build_draft_client",
]
