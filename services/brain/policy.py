from __future__ import annotations

from dataclasses import dataclass

from services.reminders.parser import looks_like_reminder

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

    # Reminders are local-only and safe; route them before the high-impact
    # check so an utterance like "remind me to send the email" still lands
    # in the reminder path rather than the approval path.
    if looks_like_reminder(normalized):
        return PolicyDecision("reminder", "Local relative reminder request.")

    if any(term in normalized.split() for term in HIGH_IMPACT_TERMS):
        return PolicyDecision(
            "approval",
            "The request may create an external or irreversible side effect.",
            requires_approval=True,
        )

    return PolicyDecision("answer", "Safe to answer directly in Phase 1.")

