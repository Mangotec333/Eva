"""In-process reminder scheduler.

The scheduler is fully synchronous-by-default and testable without real
sleeps: pass a fake `Clock` and call `run_due(now)` to drain jobs whose
fire time has arrived. For live CLI use, call `start_async()` to attach
an asyncio task that wakes at each due time.

There is no background daemon and no persistence — reminders only live for
the lifetime of the current process, matching the task scope.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    """Wall-clock time via `time.monotonic`. Monotonic so wall-clock jumps
    cannot retroactively skip or duplicate reminders within a session."""

    def now(self) -> float:
        import time

        return time.monotonic()


ReminderSink = Callable[["ReminderJob"], None]


@dataclass(order=True)
class ReminderJob:
    """A scheduled reminder. `seq` breaks ties for stable FIFO ordering."""

    fire_at: float
    seq: int = field(compare=True)
    message: str = field(compare=False)
    job_id: str = field(compare=False)


class ReminderScheduler:
    """Min-heap of reminder jobs. Thread-safe for the live `start_async` path."""

    def __init__(self, clock: Clock | None = None, sink: ReminderSink | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._sink: ReminderSink | None = sink
        self._heap: list[ReminderJob] = []
        self._lock = threading.Lock()
        self._counter = itertools.count()
        self._wake: asyncio.Event | None = None

    def set_sink(self, sink: ReminderSink) -> None:
        """Install or replace the callable that fires due jobs."""
        self._sink = sink

    def schedule(self, *, delay_seconds: float, message: str, job_id: str) -> ReminderJob:
        """Add a job that should fire `delay_seconds` from `clock.now()`."""
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if not message:
            raise ValueError("message must be non-empty")

        fire_at = self._clock.now() + delay_seconds
        job = ReminderJob(
            fire_at=fire_at,
            seq=next(self._counter),
            message=message,
            job_id=job_id,
        )
        with self._lock:
            heapq.heappush(self._heap, job)
            if self._wake is not None:
                # Wake the live runner so it re-checks its sleep horizon.
                self._wake.set()
        return job

    def pending(self) -> list[ReminderJob]:
        """Snapshot of pending jobs in fire-order. For tests/inspection."""
        with self._lock:
            return sorted(self._heap)

    def run_due(self, now: float | None = None) -> list[ReminderJob]:
        """Pop and fire every job whose `fire_at <= now`. Returns fired jobs.

        This is the test seam — drive it from a fake clock to validate that
        a scheduled reminder fires at the right virtual time, with no real
        sleeping involved.
        """
        current = now if now is not None else self._clock.now()
        fired: list[ReminderJob] = []
        with self._lock:
            while self._heap and self._heap[0].fire_at <= current:
                fired.append(heapq.heappop(self._heap))

        # Sink is invoked outside the lock so a slow speaker cannot block
        # other callers from scheduling new jobs.
        if self._sink is not None:
            for job in fired:
                self._sink(job)
        return fired

    def next_fire_at(self) -> float | None:
        with self._lock:
            return self._heap[0].fire_at if self._heap else None

    async def start_async(self, stop_event: asyncio.Event | None = None) -> None:
        """Run an asyncio loop that fires due jobs until `stop_event` is set.

        Sleeps just long enough to reach the next job's fire_at. Wakes early
        whenever a new job is scheduled so the horizon updates cheaply.
        """
        self._wake = asyncio.Event()
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                self._wake.clear()
                next_at = self.next_fire_at()
                if next_at is None:
                    sleep_for = 60.0
                else:
                    sleep_for = max(0.0, next_at - self._clock.now())
                if sleep_for > 0:
                    waiters = [asyncio.create_task(self._wake.wait())]
                    if stop_event is not None:
                        waiters.append(asyncio.create_task(stop_event.wait()))
                    try:
                        await asyncio.wait(
                            waiters,
                            timeout=sleep_for,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    finally:
                        for w in waiters:
                            w.cancel()
                if stop_event is not None and stop_event.is_set():
                    return
                self.run_due()
        finally:
            self._wake = None
