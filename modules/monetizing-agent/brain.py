"""
EVA Monetizing Agent — reasoning brain seam (swap-and-play)
===========================================================

This replaces Yaksha's direct OpenAI call with a provider-agnostic Protocol so
the packaging brain can be re-plugged without touching the scan loop, exactly as
the standing "swap-and-play" rule requires (agents depend on Protocols, never on
concrete providers).

- ``MonetizationBrain`` is the Protocol the scan loop depends on. Its single
  method ``package(play)`` turns a matched signal into a concrete, ready-to-ship
  artifact (drafted SMS/email text, pipeline move, proposal path, contact list,
  or a human-only task).
- ``StubMonetizationBrain`` is the OFFLINE implementation used in tests. It is
  fully deterministic (no network, tokens=0) and produces real artifacts from
  templates keyed by play type — so the whole scan pipeline is testable without
  any API key.
- ``LLMMonetizationBrain`` wraps the shared reasoning brain
  (``services.remote.claude`` / ``BrainClient``) for the real path. If no key is
  configured it degrades to the Stub's deterministic templates rather than
  failing — the numeric scoring + packaging core never depends on a live model.

The deterministic scoring engine (``scoring.py``) is authoritative and free; the
brain only enriches the *packaging* language. It never changes scores or ranks.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional, Protocol, runtime_checkable

# Reach the repo root so the shared reasoning transport is importable when the
# module runs "flat" (cwd = this dir), mirroring deal-analyzer-agent/agent.py.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Artifact templates (deterministic, offline)
# ---------------------------------------------------------------------------

def _draft_for(play_type: str, signal: dict) -> dict[str, Any]:
    """Return a concrete artifact for a play. Pure, deterministic, no network."""
    subject = signal.get("subject", signal.get("name", "there"))
    desc = signal.get("description", "")

    if play_type == "Reactivate":
        return {
            "kind": "sms",
            "channel": "ghl_sms",
            "to": subject,
            "text": (
                f"Hi {subject} — circling back on {desc or 'our last conversation'}. "
                "Still worth 15 min this week? I can send times."
            ),
            "route": "ghl_pipeline",
        }
    if play_type == "Upsell":
        return {
            "kind": "email",
            "channel": "ghl_email",
            "to": subject,
            "subject": "A next step that fits what you're already doing",
            "text": (
                f"{subject}, based on how you've been using this, the next tier would "
                "save you the manual work. Want me to turn it on for a 2-week trial?"
            ),
            "route": "ghl_pipeline",
        }
    if play_type == "Outreach":
        return {
            "kind": "sms",
            "channel": "ghl_sms",
            "to": subject,
            "text": (
                f"Hi {subject} — you joined the waitlist for Eva. We just opened a spot. "
                "Want a quick walkthrough this week?"
            ),
            "route": "ghl_pipeline",
        }
    if play_type == "Productize":
        return {
            "kind": "proposal_doc",
            "channel": "drive",
            "title": f"Productized offer — {desc or subject}",
            "outline": [
                "What it is (1 paragraph)",
                "Who it's for",
                "Price + package tiers",
                "Delivery / SLA",
            ],
            "route": "drive_kb",
        }
    if play_type == "Revive":
        return {
            "kind": "email",
            "channel": "ghl_email",
            "to": subject,
            "subject": "New angle on what we discussed",
            "text": (
                f"{subject}, the timing may be better now — we've since shipped the piece "
                "that was the blocker. Worth another look?"
            ),
            "route": "ghl_pipeline",
        }
    if play_type == "Referral":
        return {
            "kind": "sms",
            "channel": "ghl_sms",
            "to": subject,
            "text": (
                f"{subject}, you've gotten real value here — who's one person who'd "
                "benefit the same way? Happy to make it easy for them."
            ),
            "route": "ghl_pipeline",
        }
    if play_type == "Content-to-offer":
        return {
            "kind": "landing_tweak",
            "channel": "content",
            "asset": desc or subject,
            "cta": "Add a single CTA: 'Reply SCOUT for a free teardown.'",
            "route": "content_engine",
        }
    if play_type == "Retainer":
        return {
            "kind": "proposal_doc",
            "channel": "drive",
            "title": f"Retainer conversion — {subject}",
            "outline": ["Recap of one-off delivered", "Monthly scope", "Retainer price"],
            "route": "drive_kb",
        }
    if play_type == "White-label":
        return {
            "kind": "human_task",
            "channel": "slack",
            "assignee": "Vineet",
            "task": f"Scope a white-label/resale unit from: {desc or subject}",
            "route": "slack_task",
        }
    # Fallback: route to a human.
    return {
        "kind": "human_task",
        "channel": "slack",
        "assignee": "Vineet",
        "task": f"Review monetization signal: {desc or subject}",
        "route": "slack_task",
    }


# ---------------------------------------------------------------------------
# Protocol + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class MonetizationBrain(Protocol):
    """Swap-and-play seam: turn a matched signal into a concrete artifact."""

    def package(self, play: dict) -> dict[str, Any]:
        """Return ``{artifact: dict, tokens: int, provider: str}``."""


class StubMonetizationBrain:
    """Offline, deterministic packaging brain (used in tests). tokens=0."""

    provider = "stub"

    def package(self, play: dict) -> dict[str, Any]:
        artifact = _draft_for(play.get("play_type", ""), play.get("signal", {}))
        return {"artifact": artifact, "tokens": 0, "provider": self.provider}


class LLMMonetizationBrain:
    """Real packaging brain backed by the shared reasoning transport.

    Uses ``services.remote.claude`` to sharpen the artifact copy. Falls back to
    the deterministic Stub templates when no key is configured or the call
    errors — the packaging core never depends on a live model.
    """

    provider = "claude"

    def __init__(self, client: Optional[Any] = None, *, model: str = "claude-sonnet-4-5",
                 max_tokens: int = 512) -> None:
        if client is None:
            from services.remote.claude import make_brain_client
            client = make_brain_client()
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._fallback = StubMonetizationBrain()

    def package(self, play: dict) -> dict[str, Any]:
        base = _draft_for(play.get("play_type", ""), play.get("signal", {}))
        system = (
            "You are the Eva Monetizing Agent's packaging layer. A deterministic "
            "scorer has ALREADY ranked this play. Sharpen ONLY the outreach copy in "
            "the given artifact; keep the same JSON shape and keys. Return JSON only."
        )
        user = (
            f"PLAY TYPE: {play.get('play_type')}\n"
            f"SIGNAL: {json.dumps(play.get('signal', {}), default=str)[:800]}\n"
            f"DRAFT ARTIFACT: {json.dumps(base, default=str)}\n"
            "Return the improved artifact JSON now."
        )
        try:
            resp = self._client.complete(
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=self._max_tokens,
                model=self._model,
            )
        except Exception:  # noqa: BLE001 — brain must never break the loop
            return self._fallback.package(play)

        if resp.get("error"):
            return self._fallback.package(play)
        artifact = _parse_artifact(resp.get("content", ""), base)
        usage = resp.get("usage") or {}
        tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return {"artifact": artifact, "tokens": tokens, "provider": self.provider}


def _parse_artifact(content: str, fallback: dict) -> dict:
    text = (content or "").strip()
    if not text:
        return fallback
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return fallback
    try:
        parsed = json.loads(text[start:end + 1])
        return parsed if isinstance(parsed, dict) else fallback
    except json.JSONDecodeError:
        return fallback


def make_brain(offline: Optional[bool] = None) -> MonetizationBrain:
    """Return the real LLM brain when a key is present, else the Stub.

    Set ``EVA_MONETIZE_OFFLINE=1`` (or pass ``offline=True``) to force the Stub.
    """
    if offline is None:
        offline = os.environ.get("EVA_MONETIZE_OFFLINE") == "1"
    if offline:
        return StubMonetizationBrain()
    try:
        from services.remote.claude import resolve_api_key
        if resolve_api_key():
            return LLMMonetizationBrain()
    except Exception:  # noqa: BLE001
        pass
    return StubMonetizationBrain()


__all__ = [
    "MonetizationBrain",
    "StubMonetizationBrain",
    "LLMMonetizationBrain",
    "make_brain",
]
