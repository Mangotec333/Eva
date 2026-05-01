from __future__ import annotations

from dataclasses import dataclass


HIGH_IMPACT_TERMS = (
    "send",
    "delete",
    "purchase",
    "buy",
    "post",
    "transfer",
    "unlock",
    "trade",
    "wire",
)


@dataclass(frozen=True)
class PolicyDecision:
    route: str
    reason: str
    requires_approval: bool = False


def route_task(utterance: str) -> PolicyDecision:
    normalized = utterance.lower().strip()
    if not normalized:
        return PolicyDecision("clarify", "No request text was captured.")

    if any(term in normalized.split() for term in HIGH_IMPACT_TERMS):
        return PolicyDecision(
            "approval",
            "The request may create an external or irreversible side effect.",
            requires_approval=True,
        )

    return PolicyDecision("answer", "Safe to answer directly in Phase 1.")

