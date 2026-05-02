"""Parser for simple relative reminders.

Supported shapes (case-insensitive, optional leading wake word "eva,"):

    remind me in 30 seconds to <message>
    remind me in 2 minutes to <message>
    remind me in 1 hour to <message>
    in 5 minutes remind me to <message>

A trailing message is required. Only seconds/minutes/hours are accepted.
Anything else raises `ReminderParseError` so the caller can surface a clear
validation message instead of falling through to the LLM path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNIT_SECONDS: dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
    "h": 3600,
}

_SUPPORTED_UNITS = "seconds, minutes, or hours"
_MAX_DELAY_SECONDS = 24 * 3600  # one day cap; keeps in-process scheduling sane.

_REMIND_TRIGGER = re.compile(r"\bremind\s+me\b", re.IGNORECASE)
_DURATION_AFTER = re.compile(
    r"\bremind\s+me\b\s*(?:in|after)?\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]+)\s+to\s+(?P<msg>.+)$",
    re.IGNORECASE,
)
_DURATION_BEFORE = re.compile(
    r"\bin\s+(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]+)\s+remind\s+me\s+to\s+(?P<msg>.+)$",
    re.IGNORECASE,
)


class ReminderParseError(ValueError):
    """Raised when an utterance looks like a reminder but cannot be parsed."""


@dataclass(frozen=True)
class ParsedReminder:
    """A validated relative reminder request."""

    delay_seconds: float
    message: str
    raw_amount: float
    raw_unit: str

    def describe_delay(self) -> str:
        """Human-friendly delay phrase, e.g. '2 minutes' or '1 second'."""
        unit = self.raw_unit.lower()
        canonical = _canonical_unit_label(unit)
        amount = self.raw_amount
        if amount == int(amount):
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:g}"
        if amount == 1:
            canonical = canonical.rstrip("s")
        return f"{amount_str} {canonical}"


def _canonical_unit_label(unit: str) -> str:
    if unit in {"s", "sec", "secs", "second", "seconds"}:
        return "seconds"
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return "minutes"
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return "hours"
    return unit


def _strip_wake_word(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in ("eva,", "eva:", "eva ", "eve,", "eve:", "eve "):
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def looks_like_reminder(utterance: str) -> bool:
    """Cheap check used by routing — does the user mention 'remind me'?"""
    return bool(_REMIND_TRIGGER.search(utterance or ""))


def parse_reminder(utterance: str) -> ParsedReminder:
    """Parse an utterance into a `ParsedReminder` or raise `ReminderParseError`.

    Only call this when `looks_like_reminder` is true. The function is strict:
    it rejects unsupported units (days, weeks), missing messages, zero/negative
    durations, and anything beyond a 24-hour cap. The error message names the
    specific problem so the caller can speak it back to the user.
    """
    if not utterance:
        raise ReminderParseError("Empty reminder request.")

    text = _strip_wake_word(utterance)
    if not _REMIND_TRIGGER.search(text):
        raise ReminderParseError(
            "Reminders must include 'remind me'. "
            f"Try: 'remind me in 2 minutes to <message>' ({_SUPPORTED_UNITS})."
        )

    match = _DURATION_AFTER.search(text) or _DURATION_BEFORE.search(text)
    if match is None:
        raise ReminderParseError(
            "I could not find a delay and a message. "
            f"Use 'remind me in <number> <unit> to <message>' where unit is {_SUPPORTED_UNITS}."
        )

    amount_raw = match.group("amount")
    unit_raw = match.group("unit")
    message = match.group("msg").strip().rstrip(".!?")

    if not message:
        raise ReminderParseError("The reminder message is empty.")

    try:
        amount = float(amount_raw)
    except ValueError as exc:  # pragma: no cover - regex guards numeric form
        raise ReminderParseError(f"Could not parse '{amount_raw}' as a number.") from exc

    unit_key = unit_raw.lower()
    if unit_key not in _UNIT_SECONDS:
        raise ReminderParseError(
            f"Unsupported time unit '{unit_raw}'. Supported: {_SUPPORTED_UNITS}."
        )

    if amount <= 0:
        raise ReminderParseError("Reminder delay must be greater than zero.")

    delay_seconds = amount * _UNIT_SECONDS[unit_key]
    if delay_seconds > _MAX_DELAY_SECONDS:
        raise ReminderParseError(
            "Reminder delay exceeds the 24-hour local cap. "
            "Pick something shorter."
        )

    return ParsedReminder(
        delay_seconds=delay_seconds,
        message=message,
        raw_amount=amount,
        raw_unit=unit_raw,
    )
