"""
EVA Retro-Agent — narrative brain seam (swap-and-play).

Mirrors ``modules/monetizing-agent/brain.py``: the reasoning model sits behind a
Protocol so it can be re-plugged without touching the retro pipeline. The crucial
invariant here is even stricter than monetizing-agent's: the deterministic engine
(``engine.py``) is the ONLY thing that sets a status, a flag, or a count. The
brain may ONLY rewrite the human-readable ``narrative`` prose — never a number.

- ``RetroBrain`` — the Protocol: ``sharpen(digest) -> {narrative, tokens, provider}``.
- ``StubRetroBrain`` — offline, deterministic (tokens=0). Returns the digest's own
  deterministic narrative unchanged, so the whole pipeline is testable with no key.
- ``LLMRetroBrain`` — wraps the shared reasoning transport (``services.remote.claude``)
  to sharpen tone only. Degrades to the Stub (verbatim deterministic narrative) on
  any error or missing key — the retro core never depends on a live model.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional, Protocol, runtime_checkable

# Reach the repo root so the shared reasoning transport is importable when the
# module runs "flat" (cwd = this dir), mirroring monetizing-agent/brain.py.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@runtime_checkable
class RetroBrain(Protocol):
    """Swap-and-play seam: sharpen ONLY the digest narrative prose."""

    def sharpen(self, digest: dict) -> dict[str, Any]:
        """Return ``{narrative: str, tokens: int, provider: str}``."""


class StubRetroBrain:
    """Offline, deterministic brain (used in tests). Returns the engine's own
    narrative unchanged — tokens=0, no network."""

    provider = "stub"

    def sharpen(self, digest: dict) -> dict[str, Any]:
        return {
            "narrative": digest.get("narrative", ""),
            "tokens": 0,
            "provider": self.provider,
        }


class LLMRetroBrain:
    """Real narrative brain backed by the shared reasoning transport.

    Sharpens ONLY the prose tone of the already-computed digest narrative. It is
    handed the deterministic status/counts as read-only context and instructed
    never to alter them. Falls back to the deterministic narrative on any error.
    """

    provider = "claude"

    def __init__(self, client: Optional[Any] = None, *, model: str = "claude-sonnet-4-5",
                 max_tokens: int = 700) -> None:
        if client is None:
            from services.remote.claude import make_brain_client
            client = make_brain_client()
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._fallback = StubRetroBrain()

    def sharpen(self, digest: dict) -> dict[str, Any]:
        base = digest.get("narrative", "")
        system = (
            "You are the Eva Weekly Retro agent's narrative layer. A deterministic "
            "engine has ALREADY decided the STATUS, every flag, and every count for "
            "this weekly retrospective. You may sharpen ONLY the prose so a busy "
            "founder reads it fast. You MUST NOT change, add, or remove any status, "
            "number, pipeline name, or blocker. Keep it terse and revenue-focused. "
            "Return the rewritten plain-text digest only — no preamble."
        )
        facts = {
            "status": digest.get("status"),
            "revenue_win": digest.get("revenue_win"),
            "shipped_count": digest.get("shipped_count"),
            "revenue_movement_count": digest.get("revenue_movement_count"),
            "priorities_addressed": digest.get("priorities_addressed"),
            "priorities_total": digest.get("priorities_total"),
        }
        user = (
            f"IMMUTABLE FACTS (do not change): {json.dumps(facts, default=str)}\n\n"
            f"DETERMINISTIC DIGEST TO SHARPEN:\n{base}\n\n"
            "Return the sharpened digest now."
        )
        try:
            resp = self._client.complete(
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=self._max_tokens,
                model=self._model,
            )
        except Exception:  # noqa: BLE001 — brain must never break the retro
            return self._fallback.sharpen(digest)

        if resp.get("error"):
            return self._fallback.sharpen(digest)
        text = (resp.get("content") or "").strip()
        if not text:
            return self._fallback.sharpen(digest)
        usage = resp.get("usage") or {}
        tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return {"narrative": text, "tokens": tokens, "provider": self.provider}


def make_brain(offline: Optional[bool] = None) -> RetroBrain:
    """Return the real LLM brain when a key is present, else the Stub.

    Set ``EVA_RETRO_OFFLINE=1`` (or pass ``offline=True``) to force the Stub.
    """
    if offline is None:
        offline = os.environ.get("EVA_RETRO_OFFLINE") == "1"
    if offline:
        return StubRetroBrain()
    try:
        from services.remote.claude import resolve_api_key
        if resolve_api_key():
            return LLMRetroBrain()
    except Exception:  # noqa: BLE001
        pass
    return StubRetroBrain()


__all__ = ["RetroBrain", "StubRetroBrain", "LLMRetroBrain", "make_brain"]
