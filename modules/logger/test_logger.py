"""Baseline offline tests for logger eva_summarize pure analytics (no network/files)."""

from datetime import date

import eva_summarize as s


def test_categorize_app_known_and_unknown():
    assert s.categorize_app("Cursor") == "coding"
    assert s.categorize_app("Google Chrome") == "browsing"
    assert s.categorize_app("Slack") == "communication"
    assert s.categorize_app("SomeRandomApp") == "other"


def test_compute_app_time_sums_focus_durations():
    events = [
        {"event_type": "window_focus", "app_name": "Cursor", "duration_seconds": 100},
        {"event_type": "window_focus", "app_name": "Cursor", "duration_seconds": 50},
        {"event_type": "idle_start"},
    ]
    totals = s.compute_app_time(events)
    assert totals["Cursor"] == 150


def test_compute_focus_score_zero_when_no_activity():
    assert s.compute_focus_score([], 0) == 0


def test_extract_sessions_groups_by_gap():
    events = [
        {"event_type": "window_focus", "app_name": "Cursor",
         "duration_seconds": 60, "timestamp": "2026-05-14T09:00:00"},
        {"event_type": "window_focus", "app_name": "Cursor",
         "duration_seconds": 60, "timestamp": "2026-05-14T09:01:00"},
    ]
    sessions = s.extract_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["primary_app"] == "Cursor"


def test_build_summary_empty_day():
    summary = s.build_summary(date(1990, 1, 1))
    assert summary["focus_score"] == 0
    assert summary["top_apps"] == []
    assert summary["total_active_minutes"] == 0
