"""
EVA Networking-Agent — autonomy guardrail.

A single, explicit whitelist governs which actions Eva may take without a human
approval step. Only two low-risk actions qualify, because they put no content in
front of another person:

    join_public_group      — joining an open community (no content created/sent).
    monitor_keyword_mention — read-only listening for ICP-relevant threads.

Everything else (post, comment, connection_request, dm, …) is content that
reaches a person and MUST route through draft() → approve() → send()/post().
The service enforces this — ``auto_action`` rejects any non-whitelisted action —
so the guardrail is code, not convention.

Whitelisted actions still execute immediately AND are logged to the append-only
outcomes ledger for auditability.
"""

from __future__ import annotations

# The one true whitelist. Membership here == "may run without approval".
AUTO_ALLOWED: frozenset[str] = frozenset({
    "join_public_group",
    "monitor_keyword_mention",
})

# Actions that always require the draft → approve → send/post loop. Listed for
# documentation/validation; anything not in AUTO_ALLOWED is gated regardless.
APPROVAL_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "post",
    "comment",
    "connection_request",
    "dm",
})


class AutonomyError(Exception):
    """Raised when an action is attempted via an auto path but is not
    whitelisted. ``code`` is stable for API translation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_auto_allowed(action: str) -> bool:
    return (action or "").strip() in AUTO_ALLOWED


def assert_auto_allowed(action: str) -> None:
    """Guard for any 'auto' execution path. Raises unless whitelisted."""
    act = (action or "").strip()
    if act not in AUTO_ALLOWED:
        raise AutonomyError(
            "not_auto_allowed",
            f"action {act!r} is not in the AUTO_ALLOWED whitelist "
            f"{sorted(AUTO_ALLOWED)}; it must go through draft → approve → "
            f"send/post before it can reach a person.",
        )


__all__ = [
    "AUTO_ALLOWED", "APPROVAL_REQUIRED_ACTIONS", "AutonomyError",
    "is_auto_allowed", "assert_auto_allowed",
]
