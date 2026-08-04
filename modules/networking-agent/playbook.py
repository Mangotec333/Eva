"""
EVA Networking-Agent — relationship playbook (Layer A + shared stage logic).

Both entity types move through a stage model and get a next-best-action:

  * contacts (individuals):  unknown → engaged → active → partner
  * groups (communities):    candidate → qualified → engaged → active → partner

``next_best_action`` returns the single most sensible move for an entity at its
current stage, drawn from a small tactic playbook, plus the stage it advances to
on success. Pure/deterministic so it's trivially testable and callable from both
the service and the CLI.
"""

from __future__ import annotations

CONTACT_STAGE_ORDER = ["unknown", "engaged", "active", "partner"]
GROUP_STAGE_ORDER = ["candidate", "qualified", "engaged", "active", "partner"]

# Per-stage next-best-action. ``action`` uses the same verbs the autonomy layer
# knows; content-bearing verbs still route through draft → approve → send/post.
_CONTACT_NBA = {
    "unknown": {
        "action": "monitor_keyword_mention",
        "tactic": "Warm up: follow, monitor their posts for an ICP-relevant hook.",
        "advances_to": "engaged",
    },
    "engaged": {
        "action": "comment",
        "tactic": "Add value in public — a specific, non-pitchy comment on their work.",
        "advances_to": "active",
    },
    "active": {
        "action": "dm",
        "tactic": "Move to 1:1 — offer the venture's free-audit CTA, no strings.",
        "advances_to": "partner",
    },
    "partner": {
        "action": "dm",
        "tactic": "Nurture: share wins, ask for intros/referrals.",
        "advances_to": "partner",
    },
}

_GROUP_NBA = {
    "candidate": {
        "action": "join_public_group",
        "tactic": "Join (if public) and observe cadence, rules, and top posters.",
        "advances_to": "qualified",
    },
    "qualified": {
        "action": "monitor_keyword_mention",
        "tactic": "Listen for ICP-relevant threads before contributing anything.",
        "advances_to": "engaged",
    },
    "engaged": {
        "action": "comment",
        "tactic": "Contribute value in threads — answer questions, share proof, no pitch.",
        "advances_to": "active",
    },
    "active": {
        "action": "post",
        "tactic": "Post a teardown / data drop that showcases the venture's edge.",
        "advances_to": "partner",
    },
    "partner": {
        "action": "post",
        "tactic": "Co-create: AMAs, partnerships, recurring value with the group owners.",
        "advances_to": "partner",
    },
}

# Broader tactic library, surfaced by plan() for context.
TACTICS = [
    {"category": "listen", "tactic": "Monitor keyword mentions across joined groups."},
    {"category": "value", "tactic": "Answer questions with specific, sourced advice."},
    {"category": "value", "tactic": "Share proprietary data / teardowns relevant to the ICP."},
    {"category": "connect", "tactic": "Send a personalised connection note referencing shared context."},
    {"category": "convert", "tactic": "Offer the venture's free-audit CTA to warm contacts."},
    {"category": "nurture", "tactic": "Ask happy partners for warm intros and referrals."},
]


def stage_order(entity_type: str) -> list[str]:
    return GROUP_STAGE_ORDER if entity_type == "group" else CONTACT_STAGE_ORDER


def next_best_action(entity_type: str, stage: str) -> dict:
    table = _GROUP_NBA if entity_type == "group" else _CONTACT_NBA
    order = stage_order(entity_type)
    key = stage if stage in table else order[0]
    nba = dict(table[key])
    nba["entity_type"] = entity_type
    nba["stage"] = key
    return nba


def advance_stage(entity_type: str, stage: str) -> str:
    """The stage an entity reaches when its current-stage action succeeds."""
    order = stage_order(entity_type)
    if stage not in order:
        return order[0]
    idx = order.index(stage)
    return order[min(idx + 1, len(order) - 1)]


__all__ = [
    "CONTACT_STAGE_ORDER", "GROUP_STAGE_ORDER", "TACTICS",
    "stage_order", "next_best_action", "advance_stage",
]
