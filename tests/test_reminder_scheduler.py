from __future__ import annotations

import asyncio

import pytest

from services.reminders.scheduler import ReminderJob, ReminderScheduler


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def test_schedule_stores_job_and_orders_by_fire_time() -> None:
    clock = FakeClock(start=100.0)
    scheduler = ReminderScheduler(clock=clock)
    scheduler.schedule(delay_seconds=30, message="later", job_id="b")
    scheduler.schedule(delay_seconds=5, message="sooner", job_id="a")

    pending = scheduler.pending()
    assert [j.job_id for j in pending] == ["a", "b"]
    assert pending[0].fire_at == 105.0
    assert pending[1].fire_at == 130.0


def test_run_due_fires_only_jobs_whose_time_has_passed() -> None:
    clock = FakeClock(start=0.0)
    fired: list[ReminderJob] = []
    scheduler = ReminderScheduler(clock=clock, sink=fired.append)
    scheduler.schedule(delay_seconds=5, message="early", job_id="a")
    scheduler.schedule(delay_seconds=20, message="late", job_id="b")

    clock.advance(5.0)
    assert [j.job_id for j in scheduler.run_due()] == ["a"]
    assert [j.message for j in fired] == ["early"]
    assert [j.job_id for j in scheduler.pending()] == ["b"]

    clock.advance(20.0)
    assert [j.job_id for j in scheduler.run_due()] == ["b"]
    assert [j.message for j in fired] == ["early", "late"]
    assert scheduler.pending() == []


def test_run_due_does_not_fire_future_jobs() -> None:
    clock = FakeClock(start=0.0)
    fired: list[ReminderJob] = []
    scheduler = ReminderScheduler(clock=clock, sink=fired.append)
    scheduler.schedule(delay_seconds=10, message="future", job_id="x")

    clock.advance(9.999)
    assert scheduler.run_due() == []
    assert fired == []


def test_schedule_rejects_negative_delay() -> None:
    scheduler = ReminderScheduler(clock=FakeClock())
    with pytest.raises(ValueError):
        scheduler.schedule(delay_seconds=-1, message="x", job_id="x")


def test_schedule_rejects_empty_message() -> None:
    scheduler = ReminderScheduler(clock=FakeClock())
    with pytest.raises(ValueError):
        scheduler.schedule(delay_seconds=1, message="", job_id="x")


def test_set_sink_replaces_callable() -> None:
    clock = FakeClock(start=0.0)
    scheduler = ReminderScheduler(clock=clock)
    fired: list[str] = []
    scheduler.set_sink(lambda job: fired.append(job.message))
    scheduler.schedule(delay_seconds=1, message="hi", job_id="x")
    clock.advance(1.0)
    scheduler.run_due()
    assert fired == ["hi"]


def test_next_fire_at() -> None:
    clock = FakeClock(start=10.0)
    scheduler = ReminderScheduler(clock=clock)
    assert scheduler.next_fire_at() is None
    scheduler.schedule(delay_seconds=5, message="x", job_id="x")
    assert scheduler.next_fire_at() == 15.0


@pytest.mark.asyncio
async def test_start_async_fires_scheduled_jobs() -> None:
    """End-to-end: start_async drives real asyncio sleeps; jobs fire."""
    scheduler = ReminderScheduler()
    fired: list[ReminderJob] = []
    scheduler.set_sink(fired.append)

    stop_event = asyncio.Event()
    runner = asyncio.create_task(scheduler.start_async(stop_event))

    scheduler.schedule(delay_seconds=0.05, message="ping", job_id="x")

    # Wait long enough for the runner to wake and fire the job.
    for _ in range(40):
        if fired:
            break
        await asyncio.sleep(0.02)

    stop_event.set()
    runner.cancel()
    try:
        await runner
    except (asyncio.CancelledError, BaseException):  # pragma: no cover
        pass

    assert [j.message for j in fired] == ["ping"]
