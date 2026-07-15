"""
EVA Deployer — resilient self-poll background loop.

Eva checks GitHub for her own updates without any external cron/launchd timer:
when the service starts it spins up one daemon thread that sleeps the poll
interval (5 hours default, ``EVA_DEPLOYER_POLL_INTERVAL_SECONDS`` to override),
fires one ``service.check()`` pass (poll → maybe safe self-deploy → gated
restart), then sleeps and repeats — forever.

Design guarantees (mirror ``modules/social-scheduler/loop.py``):

  * **Resilient** — every tick is wrapped at two levels; a failing check
    (network, git, launcher, anything) is caught, logged, and the loop keeps
    going. It never crashes the service — which matters doubly here because a
    crash would leave Eva unable to update herself.
  * **Offline-safe** — with ``EVA_DEPLOYER_OFFLINE=1`` the loop no-ops:
    ``start()`` spawns no thread and ``fire()`` does nothing real.

``sleep_fn`` is injectable so tests drive the loop deterministically with zero
real time spent and zero network.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import deployer as dep

logger = logging.getLogger("deployer.loop")


class DeployerLoop:
    """One daemon thread that fires ``service.check()`` every poll interval."""

    def __init__(self, service, *, offline: Optional[bool] = None,
                 interval: Optional[float] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 error_backoff: float = 60.0) -> None:
        self.service = service
        self.offline = offline if offline is not None else getattr(service, "offline", False)
        self.interval = interval if interval is not None else float(dep.poll_interval_seconds())
        self._sleep_fn = sleep_fn
        self.error_backoff = error_backoff
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.fires: list[dict] = []  # outcome of each tick (introspection/tests)

    # -- helpers -------------------------------------------------------------

    def _sleep(self, secs: float) -> None:
        if self._sleep_fn is not None:
            self._sleep_fn(secs)
        else:
            # interruptible sleep: stop() wakes it immediately
            self._stop.wait(timeout=max(secs, 0.0))

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- one tick ------------------------------------------------------------

    def fire(self) -> dict:
        """Fire one check() pass. NEVER raises (check() is already guarded)."""
        if self.offline:
            outcome = {"ok": True, "fired": False, "offline": True}
            self.fires.append(outcome)
            return outcome
        try:
            res = self.service.check()
            outcome = {"ok": bool(res.get("ok")), "fired": True,
                       "action": res.get("action")}
        except Exception as exc:  # noqa: BLE001 — defense in depth
            logger.exception("deployer loop tick failed; continuing")
            outcome = {"ok": False, "fired": False,
                       "error": f"{type(exc).__name__}: {exc}"}
        self.fires.append(outcome)
        return outcome

    # -- thread body ---------------------------------------------------------

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self._sleep(self.interval)
                if self._stop.is_set():
                    break
                self.fire()
            except Exception:  # noqa: BLE001 — outer guard; never let the thread die
                logger.exception("deployer loop iteration crashed; backing off")
                self._sleep(self.error_backoff)

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        """Start the background thread. No-op (returns False) when offline."""
        if self.offline:
            logger.info("deployer loop: offline → not started (does nothing real)")
            return False
        if self.is_running():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="deployer-loop", daemon=True)
        self._thread.start()
        logger.info("deployer loop started (interval=%ss)", self.interval)
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


__all__ = ["DeployerLoop"]
