"""
EVA IP-Scout — daily incremental triage loop.

One daemon thread that, every 24h, runs an incremental prior-art triage over all
pending invention ideas (``service.scan()``) and writes the daily markdown
report. It NEVER files anything — L1 autonomy end to end.

Design mirrors ``modules/brand-builder/loop.py``:
  * Resilient — every tick is wrapped in try/except; a failing scan is caught,
    logged, and the loop keeps going. It never crashes the service.
  * Offline-safe — with ``EVA_IP_OFFLINE=1`` the loop no-ops (``start()`` does not
    spawn a thread).
  * Injectable ``sleep_fn`` so tests drive it deterministically, zero real time.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("ip_scout.loop")

DAY_SECONDS = 86400


class TriageLoop:
    """Daemon thread firing ``service.scan()`` once per day."""

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
        """Run one triage pass. NEVER raises."""
        try:
            res = self.service.scan()
            outcome = {"ok": True, **{k: v for k, v in res.items() if k != "disclosures"}}
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.exception("ip-scout scan tick failed; continuing")
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
                logger.exception("ip-scout loop iteration crashed; backing off")
                self._sleep(self.error_backoff)

    def start(self) -> bool:
        if self.offline:
            logger.info("ip-scout loop: offline → not started")
            return False
        if self.is_running():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="ip-scout-loop", daemon=True)
        self._thread.start()
        logger.info("ip-scout triage loop started (every %ss)", self.interval)
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


__all__ = ["TriageLoop", "DAY_SECONDS"]
