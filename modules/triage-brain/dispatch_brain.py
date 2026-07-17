"""
EVA Diracatron — the dispatch brain (Elon-style first-principles planner)
========================================================================

This is Eva's *decision* layer. Given a goal/intent in plain language, it uses
the shared reasoning brain (``services/remote/claude`` — the repo's canonical
LLM client seam, same one the monetizing-agent uses) to decide **which lobes to
invoke, in what order, with what payloads** — reasoning from first principles,
Elon-style: reduce to fundamentals, delete unnecessary steps, pick the highest-
leverage action, and act.

Design contract (mirrors the rest of Eva):

  * The LLM is asked for **JSON only** — a ranked list of steps, each
    ``{agent, action, payload, rationale}`` drawn *only* from the registry.
  * When no API key is configured (the sandbox default) or the model errors or
    returns junk, we degrade to a **deterministic heuristic planner** — the
    dispatch brain never crashes the orchestrator; it always returns a plan.
  * Nothing is fired here. The brain only *plans*; the service executes the
    plan through the registry's Invoker and logs every step to eva-state.

Stdlib only. The Claude transport is itself stdlib ``urllib`` behind the seam.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional, Protocol, runtime_checkable

from registry import AgentRegistry

# Reach the repo root so the shared reasoning transport is importable when the
# module runs "flat" (cwd = this dir), mirroring modules/monetizing-agent/brain.py.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

DEFAULT_MODEL = os.environ.get("EVA_DIRACATRON_MODEL", "claude-sonnet-4-5")

# The first-principles operating doctrine handed to the model as its system
# prompt. It is Eva's orchestrator persona — the Elon Musk Advisor + PM function
# folded in, so there is exactly ONE triage brain.
FIRST_PRINCIPLES_SYSTEM = (
    "You are Diracatron, Eva's single top-level orchestrator and dispatcher. "
    "You fold in the Elon Musk-style advisor and the product-manager function: "
    "there are no competing triage brains — you decide.\n\n"
    "Reason from FIRST PRINCIPLES, not analogy:\n"
    "1. Reduce the goal to the underlying physics — what actually has to be "
    "true for it to be done? Question every requirement; the best step is often "
    "the one you can DELETE.\n"
    "2. Pick the smallest set of highest-leverage actions. Prefer money-in and "
    "unblocking humans-who-are-waiting over busywork.\n"
    "3. Only invoke agents that exist in the provided registry, using only their "
    "listed actions. Never invent an agent, action, or route.\n"
    "4. Be ruthless: if the goal needs one agent, return one step. Do not pad.\n\n"
    "Return STRICT JSON only, no prose, of the form:\n"
    '{"steps": [{"agent": "<slug>", "action": "<action>", '
    '"payload": {..}, "rationale": "<one first-principles sentence>"}], '
    '"rationale": "<overall first-principles read of the goal>"}'
)


@runtime_checkable
class Planner(Protocol):
    def plan(self, goal: str, *, context: Optional[dict] = None) -> dict: ...


# ---------------------------------------------------------------------------
# Heuristic fallback — deterministic keyword routing over the registry. This is
# what runs offline / when the model is unavailable, so a goal is ALWAYS turned
# into an executable plan.
# ---------------------------------------------------------------------------

# Ordered (keywords -> preferred agent slug). First match wins per goal; if the
# slug is absent from the registry it is skipped, so the config stays the source
# of truth even for the fallback.
_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("deal", "acqui", "target", "listing", "score", "shortlist"), "deal-scout"),
    (("lead", "broker", "prospect", "funnel", "crm", "ghl"), "ghl-agent"),
    (("content", "draft", "write", "article", "video"), "content-engine"),
    (("brand", "brief", "positioning", "strategy"), "brand-builder"),
    (("post", "schedule", "publish", "tweet", "linkedin"), "social-scheduler"),
    (("channel", "dm", "message", "outreach"), "channels"),
    (("spend", "budget", "burn", "cost", "finance", "money"), "treasurer"),
    (("deploy", "release", "ship", "restart"), "deployer"),
    (("patent", "ip", "invention", "prior art"), "ip-scout"),
    (("run", "exec", "git", "local", "command"), "local-exec"),
    (("patterns", "activity", "context", "today"), "context-api"),
    (("playbook", "knowledge", "doc"), "knowledge"),
    (("say", "speak", "voice", "aloud"), "voice"),
]


class HeuristicPlanner:
    """Deterministic first-principles-ish router: pick the one lobe whose
    capability best matches the goal, and invoke its default action."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def plan(self, goal: str, *, context: Optional[dict] = None) -> dict:
        g = (goal or "").lower()
        steps: list[dict] = []
        for keywords, slug in _HEURISTICS:
            if any(k in g for k in keywords) and self.registry.get(slug):
                agent = self.registry.get(slug)
                steps.append({
                    "agent": slug,
                    "action": agent.default_action,
                    "payload": {"goal": goal, **(context or {})},
                    "rationale": f"Goal keywords map to {slug}; invoke its "
                                 f"'{agent.default_action}' as the highest-"
                                 f"leverage first step.",
                })
                break
        rationale = ("Heuristic plan (no LLM): reduced the goal to its nearest "
                     "capability in the registry.")
        if not steps:
            rationale = ("Heuristic plan: no lobe clearly owns this goal — "
                         "surfacing for human triage instead of guessing.")
        return {"steps": steps, "rationale": rationale, "planner": "heuristic"}


# ---------------------------------------------------------------------------
# LLM planner — first-principles decision via the shared reasoning brain.
# ---------------------------------------------------------------------------

class LLMPlanner:
    """Elon-style first-principles planner backed by ``services/remote/claude``.

    Falls back to :class:`HeuristicPlanner` whenever the model is unavailable or
    returns something that is not a valid, registry-grounded plan.
    """

    def __init__(self, registry: AgentRegistry, client: Optional[Any] = None,
                 *, model: str = DEFAULT_MODEL, max_tokens: int = 900) -> None:
        self.registry = registry
        self.model = model
        self.max_tokens = max_tokens
        self._fallback = HeuristicPlanner(registry)
        if client is None:
            from services.remote.claude import make_brain_client
            client = make_brain_client()
        self._client = client

    def plan(self, goal: str, *, context: Optional[dict] = None) -> dict:
        user = (
            f"GOAL / INTENT:\n{goal}\n\n"
            f"CONTEXT:\n{json.dumps(context or {}, default=str)[:1200]}\n\n"
            f"AGENT REGISTRY (the only agents/actions you may use):\n"
            f"{self.registry.describe()}\n\n"
            "Decide the plan now. JSON only."
        )
        try:
            resp = self._client.complete(
                system=FIRST_PRINCIPLES_SYSTEM,
                messages=[{"role": "user", "content": user}],
                max_tokens=self.max_tokens,
                model=self.model,
            )
        except Exception:  # noqa: BLE001 — brain must never break the loop
            return self._fallback.plan(goal, context=context)

        if not isinstance(resp, dict) or resp.get("error"):
            return self._fallback.plan(goal, context=context)

        parsed = _parse_plan(resp.get("content", ""))
        if parsed is None:
            return self._fallback.plan(goal, context=context)

        steps = self._validate_steps(parsed.get("steps", []), goal, context)
        if not steps:
            return self._fallback.plan(goal, context=context)
        return {"steps": steps,
                "rationale": parsed.get("rationale", ""),
                "planner": "llm", "model": self.model}

    def _validate_steps(self, raw_steps: Any, goal: str,
                        context: Optional[dict]) -> list[dict]:
        """Keep only steps that name a real agent + a real action for it.

        This is the guardrail: the LLM can only dispatch what the registry
        actually declares, so a hallucinated agent/action is dropped rather
        than fired.
        """
        out: list[dict] = []
        if not isinstance(raw_steps, list):
            return out
        for step in raw_steps:
            if not isinstance(step, dict):
                continue
            slug = step.get("agent")
            agent = self.registry.get(slug) if slug else None
            if agent is None:
                continue
            action = step.get("action") or agent.default_action
            if action not in agent.actions:
                action = agent.default_action
            if not action:
                continue
            payload = step.get("payload")
            if not isinstance(payload, dict):
                payload = {"goal": goal, **(context or {})}
            out.append({"agent": slug, "action": action, "payload": payload,
                        "rationale": step.get("rationale", "")})
        return out


def _parse_plan(content: str) -> Optional[dict]:
    """Extract the JSON plan object from a model response (tolerant of fences)."""
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def build_planner(registry: AgentRegistry,
                  offline: Optional[bool] = None) -> Planner:
    """LLM planner when a key is present, else the deterministic heuristic.

    Set ``EVA_DIRACATRON_OFFLINE=1`` (sandbox default) to force the heuristic.
    """
    if offline is None:
        offline = os.environ.get("EVA_DIRACATRON_OFFLINE") == "1"
    if offline:
        return HeuristicPlanner(registry)
    return LLMPlanner(registry)


__all__ = [
    "Planner", "HeuristicPlanner", "LLMPlanner", "build_planner",
    "FIRST_PRINCIPLES_SYSTEM",
]
