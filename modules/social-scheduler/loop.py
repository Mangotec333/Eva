"""
EVA Social-Scheduler — resilient self-fire background loop.

The scheduler doesn't need cron or launchd timers to publish on time: when the
service starts it spins up one daemon thread that computes the next ET slot
(08:00/11:00/14:00/15:00/17:00 America/New_York via ``scheduler``), sleeps until
it, then fires one ``service.run()`` pass (submit due → publish approved → LIKE +
CTA). Then it computes the next slot and repeats — forever.

Design guarantees:

  * **Resilient** — every tick is wrapped in try/except at two levels. A failing
    run() (network, gate, anything) is caught, logged, emitted to eva-state, and
    the loop keeps going. It never crashes the service.
  * **Idempotent** — a double-fire is safe: the store dedupes queued headlines by
    ``headline_hash`` and the gate approves per post, so re-running a slot cannot
    double-post.
  * **Offline-safe** — when ``EVA_SOCIAL_SCHEDULER_OFFLINE=1`` (the sandbox
    default) the loop no-ops: ``start()`` does not spawn a thread and ``fire()``
    fires nothing real.

Slot math is pure and injectable (``now_fn``/``sleep_fn``) so the whole thing is
testable offline with zero real time spent and zero network.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

import scheduler

logger = logging.getLogger("social_scheduler.loop")


def next_slot_datetime(now: datetime | None = None) -> datetime:
    """The next ET slot datetime strictly after ``now`` (tomorrow's 1st if past)."""
    now_et = scheduler.now_et(now)
    today = now_et.strftime("%Y-%m-%d")
    for slot in scheduler.SLOTS:
        dt = scheduler.slot_datetime(today, slot)
        if dt > now_et:
            return dt
    tomorrow = (now_et + timedelta(days=1)).strftime("%Y-%m-%d")
    return scheduler.slot_datetime(tomorrow, scheduler.SLOTS[0])


def seconds_until_next_slot(now: datetime | None = None) -> float:
    """Non-negative seconds to sleep until the next ET slot."""
    now_et = scheduler.now_et(now)
    return max(0.0, (next_slot_datetime(now_et) - now_et).total_seconds())


class SchedulerLoop:
    """One daemon thread that fires ``service.run()`` at each ET slot.

    ``sleep_fn`` / ``now_fn`` are injectable so tests drive the loop
    deterministically without real sleeping or wall-clock coupling.
    """

    def __init__(self, service, *, offline: Optional[bool] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 now_fn: Optional[Callable[[], datetime]] = None,
                 error_backoff: float = 30.0) -> None:
        self.service = service
        self.offline = offline if offline is not None else getattr(service, "offline", False)
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self.error_backoff = error_backoff
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.fires: list[dict] = []  # outcome of each tick (introspection/tests)

    # -- helpers -------------------------------------------------------------

    def _now(self) -> datetime:
        return self._now_fn() if self._now_fn else scheduler.now_et()

    def _sleep(self, secs: float) -> None:
        if self._sleep_fn is not None:
            self._sleep_fn(secs)
        else:
            # interruptible sleep: stop() wakes it immediately
            self._stop.wait(timeout=max(secs, 0.0))

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- one tick ------------------------------------------------------------

    def fire(self, now: datetime | None = None) -> dict:
        """Fire one run() pass with full error handling. NEVER raises.

        Offline → no-op (fires nothing real). On error → logs + emits
        ``loop_fire_failed`` to eva-state and returns an error outcome so the
        loop can keep going.
        """
        if self.offline:
            outcome = {"ok": True, "fired": False, "offline": True}
            self.fires.append(outcome)
            return outcome

        slot_iso = scheduler.now_et(now).isoformat()
        try:
            res = self.service.run(now=now)
            submitted = res.get("submitted", []) or []
            published = [p for p in (res.get("published", []) or []) if p.get("approved")]
            summary = (f"Loop fired @ {slot_iso}: {len(submitted)} submitted, "
                       f"{len(published)} published")
            self._emit("loop_fired", summary,
                       {"submitted": len(submitted), "published": len(published),
                        "fired_at": slot_iso})
            outcome = {"ok": True, "fired": True, "submitted": len(submitted),
                       "published": len(published), "fired_at": slot_iso}
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.exception("social-scheduler loop tick failed; continuing")
            self._emit("loop_fire_failed", f"Loop tick failed @ {slot_iso}: {exc}",
                       {"error": f"{type(exc).__name__}: {exc}", "fired_at": slot_iso})
            outcome = {"ok": False, "fired": False,
                       "error": f"{type(exc).__name__}: {exc}", "fired_at": slot_iso}
        self.fires.append(outcome)
        return outcome

    def _emit(self, event_type: str, summary: str, payload: dict) -> None:
        """Best-effort eva-state emit; a ledger outage must not break the loop."""
        try:
            self.service.state.emit(event_type=event_type, summary=summary,
                                    entity_id="social-scheduler-loop", payload=payload)
        except Exception:  # noqa: BLE001
            logger.exception("social-scheduler loop: state emit failed (ignored)")

    # -- thread body ---------------------------------------------------------

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self._sleep(seconds_until_next_slot(self._now()))
                if self._stop.is_set():
                    break
                self.fire(now=self._now())
            except Exception:  # noqa: BLE001 — outer guard; never let the thread die
                logger.exception("social-scheduler loop iteration crashed; backing off")
                self._sleep(self.error_backoff)

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        """Start the background thread. No-op (returns False) when offline."""
        if self.offline:
            logger.info("social-scheduler loop: offline → not started (fires nothing real)")
            return False
        if self.is_running():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="social-scheduler-loop", daemon=True)
        self._thread.start()
        logger.info("social-scheduler loop started")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


__all__ = ["SchedulerLoop", "next_slot_datetime", "seconds_until_next_slot"]
