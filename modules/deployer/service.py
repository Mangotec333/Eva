"""
EVA Deployer — service layer (poll → safe pull → diff → gated restart → log).

Wires the ``deployer`` seams (git, launcher, in-flight gate, eva-state) into one
``check()`` pass and keeps a bounded in-memory history of every pass so
``/deployer/status`` and ``/deployer/history`` can report what Eva has done to
herself. All transport is injected → runs fully offline in tests.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Callable, Optional

import deployer as dep
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("deployer.service")

HISTORY_MAX = 100


class DeployerService:
    def __init__(self, *,
                 state: Optional[StateLedgerClient] = None,
                 git: Optional[dep.GitClient] = None,
                 launcher: Optional[dep.LauncherClient] = None,
                 gate: Optional[dep.InFlightGate] = None,
                 module_map: Optional[dict[str, str]] = None,
                 offline: Optional[bool] = None,
                 restart_max_attempts: int = 12,
                 restart_backoff: float = 5.0,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_DEPLOYER_OFFLINE") == "1")
        self.state = state or build_state_client(offline=self.offline)
        # Real transport is only built when live; offline leaves them None so a
        # check is provably a no-op (nothing to call).
        self.git = git or (None if self.offline else dep.build_git_client())
        self.launcher = launcher or (None if self.offline else dep.build_launcher_client())
        self.gate = gate or (None if self.offline else dep.build_inflight_gate())
        self.module_map = module_map
        self.restart_max_attempts = restart_max_attempts
        self.restart_backoff = restart_backoff
        self._sleep_fn = sleep_fn
        self._history: deque[dict] = deque(maxlen=HISTORY_MAX)
        self._last_check_at: Optional[str] = None

    # -- introspection -------------------------------------------------------

    def status(self) -> dict:
        local = ""
        if self.git is not None:
            try:
                local = self.git.current_sha()
            except Exception as exc:  # noqa: BLE001
                logger.debug("status: current_sha failed: %s", exc)
        last = self._history[-1] if self._history else None
        return {
            "module": "eva-deployer",
            "offline": self.offline,
            "repo": dep.REPO,
            "branch": dep.BRANCH,
            "local_sha": local,
            "poll_interval_seconds": dep.poll_interval_seconds(),
            "last_check_at": self._last_check_at,
            "last_result": last,
            "history_count": len(self._history),
        }

    def history(self, limit: int = 20) -> dict:
        items = list(self._history)[-max(1, limit):]
        return {"count": len(self._history), "items": list(reversed(items))}

    # -- the deploy pass -----------------------------------------------------

    def check(self) -> dict:
        """One poll → (maybe) safe self-deploy pass. NEVER raises."""
        self._last_check_at = _now_iso()
        try:
            result = self._check()
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.exception("deployer check crashed; continuing")
            result = {"action": "error", "ok": False,
                      "error": f"{type(exc).__name__}: {exc}"}
            self._emit("deploy_failed", f"Deployer check crashed: {exc}", result)
        result["checked_at"] = self._last_check_at
        self._history.append(result)
        return result

    def _check(self) -> dict:
        if self.offline or self.git is None:
            return {"action": "noop_offline", "ok": True, "offline": True}

        local = self.git.current_sha()
        remote = self.git.remote_sha()
        if not remote:
            out = {"action": "check_failed", "ok": False, "local_sha": local,
                   "error": "could not resolve remote SHA (gh/ls-remote failed)"}
            self._emit("deploy_check_failed", "Could not resolve remote SHA", out)
            return out
        if local == remote:
            return {"action": "up_to_date", "ok": True, "local_sha": local,
                    "remote_sha": remote}

        # main is ahead → attempt a fast-forward-only self-deploy
        return self._deploy(local, remote)

    def _deploy(self, local: str, remote: str) -> dict:
        pull = self.git.pull_ff_only()
        old_sha, new_sha = pull.get("old_sha", local), pull.get("new_sha", local)

        if pull.get("conflict"):
            out = {"action": "deploy_skipped_conflict", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "error": pull.get("error", "non-fast-forward")}
            self._emit("deploy_skipped_conflict",
                       "Self-deploy aborted: non-fast-forward / conflict — kept running",
                       out)
            return out
        if not pull.get("ok"):
            out = {"action": "deploy_failed", "ok": False, "old_sha": old_sha,
                   "new_sha": new_sha, "remote_sha": remote,
                   "error": pull.get("error", "pull failed")}
            self._emit("deploy_failed", f"Self-deploy pull failed: {out['error']}", out)
            return out

        changed = self.git.changed_files(old_sha, new_sha)
        services = dep.map_files_to_services(changed, self.module_map)
        restarts = self._restart_services(services)

        all_ok = all(r.get("ok") for r in restarts)
        out = {
            "action": "deploy_applied" if all_ok else "deploy_failed",
            "ok": all_ok,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "changed_files": changed,
            "services": services,
            "restarts": restarts,
        }
        if all_ok:
            self._emit("deploy_applied",
                       f"Self-deployed {old_sha[:7]}→{new_sha[:7]}; "
                       f"restarted {len(services)} service(s): {', '.join(services) or 'none'}",
                       out)
        else:
            self._emit("deploy_failed",
                       f"Self-deployed {old_sha[:7]}→{new_sha[:7]} but a restart failed",
                       out)
        return out

    def _restart_services(self, services: list[str]) -> list[dict]:
        out: list[dict] = []
        for svc in services:
            wait = dep.wait_until_free(
                self.gate, max_attempts=self.restart_max_attempts,
                backoff=self.restart_backoff, sleep_fn=self._sleep_fn) \
                if self.gate is not None else {"free": True, "attempts": 0}
            if not wait.get("free"):
                # in-flight after bounded retries → skip; leave it running
                out.append({"service": svc, "ok": False, "restarted": False,
                            "reason": "in_flight_timeout", "wait": wait})
                continue
            if self.launcher is None:
                out.append({"service": svc, "ok": False, "restarted": False,
                            "reason": "no_launcher"})
                continue
            res = self.launcher.restart(svc)
            out.append({"service": svc, "ok": bool(res.get("ok")),
                        "restarted": bool(res.get("ok")), "wait": wait,
                        "result": res})
        return out

    # -- eva-state -----------------------------------------------------------

    def _emit(self, event_type: str, summary: str, payload: dict) -> None:
        """Best-effort eva-state emit; a ledger outage must not break a deploy."""
        try:
            self.state.emit(event_type=event_type, summary=summary,
                            entity_id="deployer", payload=payload)
        except Exception:  # noqa: BLE001
            logger.exception("deployer: state emit failed (ignored)")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


__all__ = ["DeployerService", "HISTORY_MAX"]
