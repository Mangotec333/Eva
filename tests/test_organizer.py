"""Unit tests for the deterministic local request organizer."""

from __future__ import annotations

from services.brain.organizer import (
    OrganizedRequest,
    RouteHint,
    TaskCategory,
    organize,
)


def test_clear_reminder_is_organized_to_local_tool() -> None:
    result = organize("remind me in 10 minutes to drink water")
    assert isinstance(result, OrganizedRequest)
    assert result.task_type is TaskCategory.REMINDER
    assert result.route_hint is RouteHint.LOCAL_TOOL
    assert result.needs_clarification is False
    assert result.due_seconds == 600
    assert result.due_text == "10 minutes"
    assert result.suggested_next_step == "schedule_local_reminder"


def test_reminder_with_wake_word_strips_ava_prefix() -> None:
    result = organize("AVA, remind me in 1 hour to call mom")
    assert result.task_type is TaskCategory.REMINDER
    assert result.normalized_goal.lower().startswith("remind me")
    assert result.due_seconds == 3600


def test_empty_request_asks_for_clarification() -> None:
    result = organize("   ")
    assert result.needs_clarification is True
    assert result.route_hint is RouteHint.CLARIFY
    assert result.task_type is TaskCategory.UNKNOWN
    assert result.clarifying_question
    assert "goal" in result.missing_information


def test_vague_request_asks_for_clarification() -> None:
    result = organize("help")
    assert result.needs_clarification is True
    assert result.route_hint is RouteHint.CLARIFY
    assert result.clarifying_question is not None


def test_high_impact_action_flags_approval() -> None:
    result = organize("send the quarterly report to the board")
    assert result.task_type is TaskCategory.HIGH_IMPACT_ACTION
    assert result.route_hint is RouteHint.APPROVAL_REQUIRED
    assert "high_impact" in result.safety_flags
    assert result.suggested_next_step == "request_user_approval"


def test_research_request_routes_to_perplexity() -> None:
    result = organize("what is the latest news on the GPU shortage")
    assert result.task_type is TaskCategory.RESEARCH
    assert result.route_hint is RouteHint.PERPLEXITY_COMPUTER


def test_build_request_routes_to_perplexity() -> None:
    result = organize("implement a small CLI that lists my notes")
    assert result.task_type is TaskCategory.BUILD
    assert result.route_hint is RouteHint.PERPLEXITY_COMPUTER


def test_local_file_request_routes_to_local_tool() -> None:
    result = organize("list files in my Downloads folder")
    assert result.task_type is TaskCategory.LOCAL_FILE
    assert result.route_hint is RouteHint.LOCAL_TOOL


def test_shell_request_routes_to_api_adapter() -> None:
    result = organize("run command git status in the project")
    assert result.task_type is TaskCategory.SHELL
    assert result.route_hint is RouteHint.API_ADAPTER


def test_browser_request_routes_to_api_adapter() -> None:
    result = organize("open website example.com and click the login button")
    assert result.task_type is TaskCategory.BROWSER
    assert result.route_hint is RouteHint.API_ADAPTER


def test_reminder_with_unparseable_duration_clarifies() -> None:
    result = organize("remind me to do the thing")
    assert result.task_type is TaskCategory.REMINDER
    assert result.needs_clarification is True
    assert result.clarifying_question is not None


def test_organize_is_deterministic_for_same_input() -> None:
    a = organize("what is the current time in Tokyo")
    b = organize("what is the current time in Tokyo")
    assert a == b


def test_high_impact_phrasing_does_not_double_match_research() -> None:
    # "delete" must win over a "what is" research hint when both would match.
    result = organize("delete the old build artifacts")
    assert result.route_hint is RouteHint.APPROVAL_REQUIRED


def test_organized_request_confidence_is_in_unit_interval() -> None:
    result = organize("hello there")
    assert 0.0 <= result.confidence <= 1.0
