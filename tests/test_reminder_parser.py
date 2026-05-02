from __future__ import annotations

import pytest

from services.reminders.parser import (
    ReminderParseError,
    looks_like_reminder,
    parse_reminder,
)


def test_looks_like_reminder_detects_phrase() -> None:
    assert looks_like_reminder("EVA, remind me in 2 minutes to test the mic")
    assert looks_like_reminder("remind   me to call back")
    assert not looks_like_reminder("what's the weather")
    assert not looks_like_reminder("")


def test_parse_reminder_minutes() -> None:
    parsed = parse_reminder("remind me in 2 minutes to test the microphone")
    assert parsed.delay_seconds == 120.0
    assert parsed.message == "test the microphone"
    assert parsed.describe_delay() == "2 minutes"


def test_parse_reminder_seconds_with_wake_word() -> None:
    parsed = parse_reminder("EVA, remind me in 10 seconds to stand up")
    assert parsed.delay_seconds == 10.0
    assert parsed.message == "stand up"
    assert parsed.describe_delay() == "10 seconds"


def test_parse_reminder_singular_units() -> None:
    parsed = parse_reminder("remind me in 1 minute to drink water.")
    assert parsed.delay_seconds == 60.0
    assert parsed.describe_delay() == "1 minute"
    assert parsed.message == "drink water"


def test_parse_reminder_hours_and_short_unit() -> None:
    parsed = parse_reminder("remind me in 1 hour to check the oven")
    assert parsed.delay_seconds == 3600.0
    parsed_short = parse_reminder("remind me in 30s to refresh")
    assert parsed_short.delay_seconds == 30.0


def test_parse_reminder_in_then_remind_form() -> None:
    parsed = parse_reminder("in 5 minutes remind me to take a break")
    assert parsed.delay_seconds == 300.0
    assert parsed.message == "take a break"


def test_parse_reminder_rejects_unsupported_unit() -> None:
    with pytest.raises(ReminderParseError, match="Unsupported time unit"):
        parse_reminder("remind me in 2 days to water plants")


def test_parse_reminder_rejects_zero_delay() -> None:
    with pytest.raises(ReminderParseError, match="greater than zero"):
        parse_reminder("remind me in 0 minutes to nothing")


def test_parse_reminder_rejects_missing_message() -> None:
    with pytest.raises(ReminderParseError):
        parse_reminder("remind me in 5 minutes")


def test_parse_reminder_rejects_no_delay() -> None:
    with pytest.raises(ReminderParseError):
        parse_reminder("remind me to call mom")


def test_parse_reminder_rejects_excessive_delay() -> None:
    with pytest.raises(ReminderParseError, match="24-hour"):
        parse_reminder("remind me in 25 hours to check")


def test_parse_reminder_rejects_non_reminder() -> None:
    with pytest.raises(ReminderParseError):
        parse_reminder("what's the weather today")


def test_parse_reminder_rejects_empty_string() -> None:
    with pytest.raises(ReminderParseError):
        parse_reminder("")
