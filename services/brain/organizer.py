"""Deterministic local request organizer.

Turns a raw user utterance into a structured ``OrganizedRequest`` that
downstream routing/executor code can consume. The organizer never calls a
model and never touches the network — it is pure heuristics so unit tests
stay cheap and the local tier remains responsive.

The organizer is a *framework* layer: it does not replace the router in
``services/brain/routing.py``. It produces a ``route_hint`` that the
router/orchestrator can use as one signal among many. Mapping the
organizer output to a real ``RouteKind`` and to executor calls happens at
the seam in the orchestrator; see ``docs/hybrid-architecture.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from services.brain.policy import HIGH_IMPACT_TERMS
from services.reminders.parser import ReminderParseError, looks_like_reminder, parse_reminder


class TaskCategory(StrEnum):
    """Coarse intent buckets the organizer can identify locally."""

    REMINDER = "reminder"
    LOCAL_FILE = "local_file"
    SHELL = "shell"
    BROWSER = "browser"
    RESEARCH = "research"
    BUILD = "build"
    HIGH_IMPACT_ACTION = "high_impact_action"
    SMALL_TALK = "small_talk"
    UNKNOWN = "unknown"


class RouteHint(StrEnum):
    """Suggested downstream route, mirroring ``RouteKind`` values.

    Kept as its own enum so the organizer is not coupled to the router's
    exact set — the router is allowed to ignore or override the hint.
    """

    LOCAL_TOOL = "local_tool"
    API_ADAPTER = "api_adapter"
    PERPLEXITY_COMPUTER = "perplexity_computer"
    DYNAMIC_BUILD = "dynamic_build"
    APPROVAL_REQUIRED = "approval_required"
    CLARIFY = "clarify"


@dataclass(frozen=True)
class OrganizedRequest:
    """Structured view of a single user utterance.

    Field semantics:

    - ``original_utterance`` — verbatim input.
    - ``normalized_goal`` — trimmed/lower-cased, wake-word stripped.
    - ``task_type`` — best-guess ``TaskCategory``.
    - ``needs_clarification`` — true when the organizer cannot proceed
      without a single targeted question.
    - ``missing_information`` — short tags listing what is missing.
    - ``clarifying_question`` — populated when ``needs_clarification``.
    - ``route_hint`` — suggested ``RouteHint``; downstream router decides.
    - ``safety_flags`` — short tags such as ``high_impact``,
      ``external_side_effect`` that callers should respect.
    - ``confidence`` — float in [0, 1]; heuristic only.
    - ``due_text`` — raw duration phrase if a reminder was parseable.
    - ``due_seconds`` — numeric delay in seconds if parseable.
    - ``suggested_next_step`` — single short imperative for the executor.
    """

    original_utterance: str
    normalized_goal: str
    task_type: TaskCategory
    needs_clarification: bool
    route_hint: RouteHint
    confidence: float
    missing_information: tuple[str, ...] = field(default_factory=tuple)
    clarifying_question: str | None = None
    safety_flags: tuple[str, ...] = field(default_factory=tuple)
    due_text: str | None = None
    due_seconds: float | None = None
    suggested_next_step: str | None = None


_WAKE_WORD = re.compile(r"^\s*(?:hey\s+)?(?:ava|eva|eve)\b[\s,]*", re.IGNORECASE)
_VAGUE_PROMPTS = {"help", "do something", "anything", "idk", "i don't know", "?"}

_LOCAL_FILE_HINTS = (
    "file",
    "files",
    "folder",
    "directory",
    "rename",
    "move file",
    "list files",
    "open file",
    "read file",
    "write file",
    "save to",
)
_SHELL_HINTS = (
    "run command",
    "shell",
    "terminal",
    "git status",
    "git log",
    "ls ",
    "grep ",
    "make ",
)
_BROWSER_HINTS = (
    "open website",
    "open url",
    "navigate to",
    "browse to",
    "click ",
    "fill the form",
    "scrape ",
)
_RESEARCH_HINTS = (
    "search ",
    "look up",
    "what is",
    "who is",
    "latest",
    "current",
    "news",
    "today",
    "explain ",
    "summarize",
    "summarise",
)
_BUILD_HINTS = (
    "build ",
    "implement ",
    "write a ",
    "create a script",
    "code ",
    "integrate ",
    "scaffold ",
    "refactor ",
    "fix the bug",
)
_SMALL_TALK = ("hello", "hi", "hey", "thanks", "thank you", "good morning", "good night")


def _normalize(utterance: str) -> str:
    text = (utterance or "").strip()
    text = _WAKE_WORD.sub("", text)
    return text.strip()


def _is_vague(normalized: str) -> bool:
    if not normalized:
        return True
    lower = normalized.lower().rstrip(".!?")
    if lower in _VAGUE_PROMPTS:
        return True
    # A bare verb with no object — e.g. "do" or "go" — is vague enough to clarify.
    if len(lower.split()) == 1 and len(lower) <= 4:
        return True
    return False


def _has_high_impact_verb(normalized_lower: str) -> bool:
    tokens = re.findall(r"[a-z]+", normalized_lower)
    return any(term in tokens for term in HIGH_IMPACT_TERMS)


def _matches_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(h in text for h in hints)


def organize(utterance: str) -> OrganizedRequest:
    """Organize ``utterance`` into a structured ``OrganizedRequest``.

    Pure function: no I/O, no model calls, no shared state. Heuristics
    are intentionally simple — the organizer's job is to give the router
    a stable, well-typed handoff, not to do real NLU.
    """

    original = utterance or ""
    normalized = _normalize(original)
    lower = normalized.lower()

    if _is_vague(normalized):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.UNKNOWN,
            needs_clarification=True,
            route_hint=RouteHint.CLARIFY,
            confidence=0.2,
            missing_information=("goal",),
            clarifying_question="What would you like me to do?",
            suggested_next_step="ask_clarifying_question",
        )

    if looks_like_reminder(lower):
        try:
            parsed = parse_reminder(original)
        except ReminderParseError as exc:
            return OrganizedRequest(
                original_utterance=original,
                normalized_goal=normalized,
                task_type=TaskCategory.REMINDER,
                needs_clarification=True,
                route_hint=RouteHint.CLARIFY,
                confidence=0.5,
                missing_information=("reminder_duration_or_message",),
                clarifying_question=(
                    "I can set a reminder, but I need a duration and a message. "
                    f"({exc})"
                ),
                suggested_next_step="ask_clarifying_question",
            )
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.REMINDER,
            needs_clarification=False,
            route_hint=RouteHint.LOCAL_TOOL,
            confidence=0.9,
            due_text=parsed.describe_delay(),
            due_seconds=parsed.delay_seconds,
            suggested_next_step="schedule_local_reminder",
        )

    if _has_high_impact_verb(lower):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.HIGH_IMPACT_ACTION,
            needs_clarification=False,
            route_hint=RouteHint.APPROVAL_REQUIRED,
            confidence=0.85,
            safety_flags=("high_impact", "external_side_effect"),
            suggested_next_step="request_user_approval",
        )

    if _matches_any(lower, _LOCAL_FILE_HINTS):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.LOCAL_FILE,
            needs_clarification=False,
            route_hint=RouteHint.LOCAL_TOOL,
            confidence=0.7,
            suggested_next_step="invoke_local_files_adapter",
        )

    if _matches_any(lower, _SHELL_HINTS):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.SHELL,
            needs_clarification=False,
            route_hint=RouteHint.API_ADAPTER,
            confidence=0.65,
            suggested_next_step="invoke_shell_adapter",
        )

    if _matches_any(lower, _BROWSER_HINTS):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.BROWSER,
            needs_clarification=False,
            route_hint=RouteHint.API_ADAPTER,
            confidence=0.6,
            suggested_next_step="invoke_browser_adapter",
        )

    if _matches_any(lower, _BUILD_HINTS):
        # Multi-step build/code work: prefer the remote brain. The router
        # may upgrade this to DYNAMIC_BUILD when the workflow is novel,
        # but PERPLEXITY_COMPUTER is the safer default per the spec.
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.BUILD,
            needs_clarification=False,
            route_hint=RouteHint.PERPLEXITY_COMPUTER,
            confidence=0.6,
            suggested_next_step="hand_off_to_perplexity_computer",
        )

    if _matches_any(lower, _RESEARCH_HINTS):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.RESEARCH,
            needs_clarification=False,
            route_hint=RouteHint.PERPLEXITY_COMPUTER,
            confidence=0.7,
            suggested_next_step="hand_off_to_perplexity_computer",
        )

    if _matches_any(lower, _SMALL_TALK):
        return OrganizedRequest(
            original_utterance=original,
            normalized_goal=normalized,
            task_type=TaskCategory.SMALL_TALK,
            needs_clarification=False,
            route_hint=RouteHint.LOCAL_TOOL,
            confidence=0.5,
            suggested_next_step="reply_locally",
        )

    return OrganizedRequest(
        original_utterance=original,
        normalized_goal=normalized,
        task_type=TaskCategory.UNKNOWN,
        needs_clarification=True,
        route_hint=RouteHint.CLARIFY,
        confidence=0.3,
        missing_information=("intent",),
        clarifying_question="Should I treat that as a question, a local task, or a reminder?",
        suggested_next_step="ask_clarifying_question",
    )
