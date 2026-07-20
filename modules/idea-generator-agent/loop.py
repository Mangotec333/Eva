"""
EVA Idea-Generator-Agent — daily alignment-check daemon.

One daemon thread that, every 24h, runs ``service.run_alignment_check()`` —
the system-wide red-flag/drift check the user asked for ("daily automated").
Design mirrors ``modules/ip-scout/loop.py`` / ``modules/brand-builder/loop.py``:

  * Resilient — every tick is wrapped in try/except; a failing check is
    caught, logged, and the loop keeps going. It never crashes the service.
  * Offline-safe — with ``EVA_IDEA_OFFLINE=1`` or ``EVA_IDEA_NO_LOOP=1`` the
    loop no-ops (``start()`` does not spawn a thread).
  * Injectable ``sleep_fn`` so tests drive it deterministically, zero real time.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

logger = logging.getLogger("idea_generator.loop")

DAY_SECONDS = 86400


class AlignmentLoop:
    """Daemon thread firing ``service.run_alignment_check()`` once per day."""

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
        """Run a single alignment-check tick synchronously (no thread). Used
        directly by tests to exercise the resilience wrapper deterministically."""
        try:
            digest = self.service.run_alignment_check()
            out = {"ok": True, "status": digest.get("status")}
        except Exception as exc:  # never let the caller crash
            logger.warning("alignment check tick failed: %s", exc)
            out = {"ok": False, "error": str(exc)}
        self.fires.append(out)
        return out

    def _run(self) -> None:
        while not self._stop.is_set():
            out = self.fire()
            self._sleep(self.error_backoff if not out["ok"] else self.interval)

    def start(self) -> bool:
        no_loop = os.environ.get("EVA_IDEA_NO_LOOP") == "1"
        if self.offline or no_loop:
            logger.info("AlignmentLoop not started (offline=%s no_loop=%s)",
                        self.offline, no_loop)
            return False
        if self.is_running():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="idea-generator-alignment-loop", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


__all__ = ["AlignmentLoop", "DAY_SECONDS"]
