"""Hybrid-architecture routing decision.

Pure function over a small structured input. Never calls a model, never
talks to the network. See ``docs/hybrid-architecture.md`` for the policy
this module implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from services.brain.policy import HIGH_IMPACT_TERMS
from services.reminders.parser import looks_like_reminder


class RouteKind(StrEnum):
    LOCAL_TOOL = "local_tool"
    API_ADAPTER = "api_adapter"
    PERPLEXITY_COMPUTER = "perplexity_computer"
    DYNAMIC_BUILD = "dynamic_build"
    EXTERNAL_AGENT = "external_agent"
    CLARIFY = "clarify"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class RoutingPolicy:
    """Operator-tunable knobs that constrain routing.

    These are deliberately coarse. The router treats them as hard gates,
    not heuristics.
    """

    allow_remote: bool = True
    allow_dynamic_build: bool = True
    allow_external_agent: bool = False
    credit_budget_remaining: int = 100


@dataclass(frozen=True)
class RoutingSignals:
    """Pre-derived observations about an utterance.

    The shell or a lightweight detector fills these in. Keeping them as
    explicit booleans (rather than re-deriving from text) makes the router
    trivially testable and lets future detectors evolve independently.
    """

    matches_known_adapter: bool = False
    requires_fresh_world_knowledge: bool = False
    novel_workflow: bool = False
    user_explicit_approval: bool = False
    prefers_external_agent: bool = False


@dataclass(frozen=True)
class RoutingInput:
    utterance: str
    signals: RoutingSignals = field(default_factory=RoutingSignals)
    policy: RoutingPolicy = field(default_factory=RoutingPolicy)


@dataclass(frozen=True)
class RoutingDecision:
    kind: RouteKind
    reason: str
    requires_approval: bool = False


_REMOTE_CREDIT_COST = 1
_DYNAMIC_CREDIT_COST = 5
_EXTERNAL_AGENT_CREDIT_COST = 1


def _looks_high_impact(utterance: str) -> bool:
    tokens = utterance.lower().split()
    return any(term in tokens for term in HIGH_IMPACT_TERMS)


def decide_route(inp: RoutingInput) -> RoutingDecision:
    """Classify ``inp`` into a single :class:`RouteKind`.

    Decision precedence is documented in ``docs/hybrid-architecture.md``
    section 5. Each branch returns a ``RoutingDecision`` with a
    human-readable reason; callers log the reason in the audit trail.
    """

    text = inp.utterance.strip()
    if not text:
        return RoutingDecision(
            RouteKind.CLARIFY,
            "Empty utterance; nothing to route.",
        )

    high_impact = _looks_high_impact(text)
    if high_impact and not inp.signals.user_explicit_approval:
        return RoutingDecision(
            RouteKind.APPROVAL_REQUIRED,
            "Utterance contains a high-impact verb without explicit pre-approval.",
            requires_approval=True,
        )

    # T0 LOCAL_TOOL — reminders are the only built-in tool today; future
    # local tools register their own ``looks_like_*`` detectors and feed
    # ``signals.matches_known_adapter`` instead.
    if looks_like_reminder(text.lower()):
        return RoutingDecision(
            RouteKind.LOCAL_TOOL,
            "Local relative reminder request.",
        )

    # T1 API_ADAPTER — caller asserts a stable local adapter handles this.
    if inp.signals.matches_known_adapter:
        return RoutingDecision(
            RouteKind.API_ADAPTER,
            "A stable local adapter matches the request.",
        )

    remote_affordable = inp.policy.credit_budget_remaining >= _REMOTE_CREDIT_COST
    dynamic_affordable = inp.policy.credit_budget_remaining >= _DYNAMIC_CREDIT_COST
    external_affordable = inp.policy.credit_budget_remaining >= _EXTERNAL_AGENT_CREDIT_COST

    # T2x EXTERNAL_AGENT — optional third-party agent (e.g. MANUS). Only
    # fires when the operator has explicitly enabled it AND the caller has
    # signalled a preference for it over the default Perplexity Computer
    # path. Otherwise we fall through to T2.
    if (
        inp.signals.prefers_external_agent
        and inp.policy.allow_external_agent
        and external_affordable
    ):
        return RoutingDecision(
            RouteKind.EXTERNAL_AGENT,
            "Operator-configured external agent is preferred for this request.",
        )

    # T2 PERPLEXITY_COMPUTER — reasoning / fresh world knowledge.
    if inp.signals.requires_fresh_world_knowledge and inp.policy.allow_remote and remote_affordable:
        return RoutingDecision(
            RouteKind.PERPLEXITY_COMPUTER,
            "Request needs reasoning or fresh world knowledge; remote brain is enabled.",
        )

    # T3 DYNAMIC_BUILD — novel multi-step workflow.
    if inp.signals.novel_workflow and inp.policy.allow_dynamic_build and dynamic_affordable:
        return RoutingDecision(
            RouteKind.DYNAMIC_BUILD,
            "Novel workflow; dynamic build enabled and budget permits.",
        )

    # Remote requested but blocked by policy or budget — degrade safely.
    if inp.signals.requires_fresh_world_knowledge or inp.signals.novel_workflow:
        return RoutingDecision(
            RouteKind.CLARIFY,
            "Remote help is needed but not available; ask the user how to proceed.",
        )

    return RoutingDecision(
        RouteKind.CLARIFY,
        "No matching local tool, adapter, or remote route; ask a clarifying question.",
    )
