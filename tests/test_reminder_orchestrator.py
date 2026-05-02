from __future__ import annotations

import pytest

from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import TaskRequest, TaskStatus
from services.model.provider import HeuristicModelProvider
from services.reminders.scheduler import ReminderScheduler


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.mark.asyncio
async def test_orchestrator_schedules_reminder_and_returns_scheduled_status() -> None:
    clock = _FakeClock(start=0.0)
    fired: list[str] = []
    scheduler = ReminderScheduler(clock=clock, sink=lambda j: fired.append(j.message))
    brain = BrainOrchestrator(HeuristicModelProvider(), reminder_scheduler=scheduler)

    response = await brain.handle(
        TaskRequest(utterance="EVA, remind me in 2 minutes to test the microphone")
    )

    assert response.status == TaskStatus.SCHEDULED
    assert "test the microphone" in response.text
    assert "2 minutes" in response.text
    assert response.artifacts == [
        {"kind": "reminder", "delay_seconds": 120.0, "message": "test the microphone"}
    ]

    pending = scheduler.pending()
    assert len(pending) == 1
    assert pending[0].fire_at == 120.0

    clock.advance(120.0)
    scheduler.run_due()
    assert fired == ["test the microphone"]


@pytest.mark.asyncio
async def test_orchestrator_returns_clarification_for_unparseable_reminder() -> None:
    scheduler = ReminderScheduler(clock=_FakeClock())
    brain = BrainOrchestrator(HeuristicModelProvider(), reminder_scheduler=scheduler)

    response = await brain.handle(
        TaskRequest(utterance="remind me in 2 days to water plants")
    )

    assert response.status == TaskStatus.NEEDS_CLARIFICATION
    assert "Unsupported time unit" in response.text
    assert scheduler.pending() == []


@pytest.mark.asyncio
async def test_orchestrator_reminder_route_bypasses_high_impact_terms() -> None:
    """A reminder whose body contains 'send' should still schedule, not require approval."""
    scheduler = ReminderScheduler(clock=_FakeClock())
    brain = BrainOrchestrator(HeuristicModelProvider(), reminder_scheduler=scheduler)

    response = await brain.handle(
        TaskRequest(utterance="remind me in 30 seconds to send the email")
    )

    assert response.status == TaskStatus.SCHEDULED
    assert len(scheduler.pending()) == 1


@pytest.mark.asyncio
async def test_orchestrator_without_scheduler_returns_failed_safe() -> None:
    brain = BrainOrchestrator(HeuristicModelProvider())  # no scheduler

    response = await brain.handle(
        TaskRequest(utterance="remind me in 1 minute to stand up")
    )

    assert response.status == TaskStatus.FAILED_SAFE
    assert "Reminders are not available" in response.text


@pytest.mark.asyncio
async def test_orchestrator_existing_safe_path_unchanged() -> None:
    brain = BrainOrchestrator(HeuristicModelProvider())
    response = await brain.handle(TaskRequest(utterance="hello eva"))
    assert response.status == TaskStatus.COMPLETED
