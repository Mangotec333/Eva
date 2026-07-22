"""
EVA Activity-Tracker-Agent — daily EOD digest daemon.

One daemon thread that, every 24h, runs ``service.run_daily_digest()`` — the
end-of-day activity log + pattern catch + course-correction the user asked
for ("at the end of the day — everyday"). Design mirrors
``modules/idea-generator-agent/loop.py`` exactly:

  * Resilient — every tick wrapped in try/except; a failing run is caught,
    logged, and the loop keeps going. Never crashes the service.
  * Offline-safe — ``EVA_ACTIVITY_OFFLINE=1`` or ``EVA_ACTIVITY_NO_LOOP=1``
    no-ops (``start()`` does not spawn a thread).
  * Injectable ``sleep_fn`` so tests drive it deterministically, zero real time.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

logger = logging.getLogger("activity_tracker.loop")

DAY_SECONDS = 86400


class DailyDigestLoop:
    """Daemon thread firing ``service.run_daily_digest()`` once per day."""

    def __init__(self, service, *, interval: float = DAY_SECONDS,
                 offline: Optional[bool] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 error_backoff: float = 300.0) -> None:
        self.service = service
        self.interval = interval
        self.offline = offline if offline is not None else getattr(service, "offline", False)
        self._sleep_fn = sleep_fn
        self.error_backoff = error_backoff
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.fires: list[dict] = []

    def _sleep(self, secs: float) -> None:
        if self._sleep_fn is not None:
            self._sleep_fn(secs)
        else:
            self._stop.wait(timeout=max(secs, 0.0))

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def fire(self) -> dict:
        """Run a single digest tick synchronously (no thread). Used directly
        by tests to exercise the resilience wrapper deterministically."""
        try:
            digest = self.service.run_daily_digest()
            out = {"ok": True, "status": digest.get("status")}
        except Exception as exc:  # never let the caller crash
            logger.warning("daily digest tick failed: %s", exc)
            out = {"ok": False, "error": str(exc)}
        self.fires.append(out)
        return out

    def _run(self) -> None:
        while not self._stop.is_set():
            out = self.fire()
            self._sleep(self.error_backoff if not out["ok"] else self.interval)

    def start(self) -> bool:
        no_loop = os.environ.get("EVA_ACTIVITY_NO_LOOP") == "1"
        if self.offline or no_loop:
            logger.info("DailyDigestLoop not started (offline=%s no_loop=%s)",
                        self.offline, no_loop)
            return False
        if self.is_running():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="activity-tracker-daily-loop", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


__all__ = ["DailyDigestLoop", "DAY_SECONDS"]
