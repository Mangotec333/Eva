"""
EVA Brand-Builder — weekly blueprint-refresh loop.

One daemon thread that, every 7 days, re-checks all stored blueprints for
staleness (``service.refresh()``): any blueprint whose ``blueprint_version`` is
older than 7 days emits a ``brand_blueprint_stale`` eva-state event so the
operator knows the market research needs refreshing.

Design mirrors ``modules/social-scheduler/loop.py``:
  * Resilient — every tick is wrapped in try/except; a failing refresh is caught,
    logged, and the loop keeps going. It never crashes the service.
  * Offline-safe — with ``EVA_BRAND_OFFLINE=1`` the loop no-ops (``start()`` does
    not spawn a thread).
  * Injectable ``sleep_fn`` so tests drive it deterministically, zero real time.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("brand_builder.loop")

WEEK_SECONDS = 86400 * 7


class RefreshLoop:
    """Daemon thread firing ``service.refresh()`` once per week."""

    def __init__(self, service, *, interval: float = WEEK_SECONDS,
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
        """Run one refresh pass. NEVER raises."""
        try:
            res = self.service.refresh()
            outcome = {"ok": True, **res}
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.exception("brand-builder refresh tick failed; continuing")
            outcome = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        self.fires.append(outcome)
        return outcome

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self._sleep(self.interval)
                if self._stop.is_set():
                    break
                self.fire()
            except Exception:  # noqa: BLE001 — outer guard; never let the thread die
                logger.exception("brand-builder loop iteration crashed; backing off")
                self._sleep(self.error_backoff)

    def start(self) -> bool:
        if self.offline:
            logger.info("brand-builder loop: offline → not started")
            return False
        if self.is_running():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="brand-builder-loop", daemon=True)
        self._thread.start()
        logger.info("brand-builder refresh loop started (every %ss)", self.interval)
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


__all__ = ["RefreshLoop", "WEEK_SECONDS"]
