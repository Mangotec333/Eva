"""
EVA Local-Exec — service layer (decide → run-or-gate → mask → audit).

Ties the "Mac hands" seams together for one request/response exec:

  1. **Allowlisted** commands (git read ops, curl-localhost, launcher restart,
     vercel --prod in a git repo, env-file token swaps) run immediately via
     ``exec.run_command`` (shell=False), get masked, and are audited as
     ``allowlisted`` (or ``failed`` on non-zero exit).
  2. **Everything else** does NOT run. It is recorded as ``pending``, a one-tap
     Slack approval request is posted (``approve.build_notifier``), and the call
     blocks until ``POST /local-exec/approve`` flips the row — then it runs
     (``approved`` / ``failed``) — or the approval window (default 300s) lapses
     and it auto-expires (``expired``, ``local_exec_expired`` emitted). It never
     runs unapproved.

Every outcome is emitted to eva-state (:8769) as a ``local_exec_*`` event and
stored in the local sqlite audit. All seams (state, notifier, clock) are injected
so the whole path runs offline in tests and executes nothing real.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

import exec as ex
import store
from approve import ApprovalNotifier, approval_link, build_notifier
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("local-exec.service")

DEFAULT_APPROVAL_TIMEOUT = 300  # seconds to wait for one-tap approval


def _now_iso() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(seconds: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class LocalExecService:
    def __init__(self, *,
                 offline: Optional[bool] = None,
                 state: Optional[StateLedgerClient] = None,
                 notifier: Optional[ApprovalNotifier] = None,
                 allowlist: Optional[list[dict]] = None,
                 db_path: Optional[str] = None,
                 approval_timeout: float = DEFAULT_APPROVAL_TIMEOUT,
                 default_exec_timeout: int = ex.DEFAULT_EXEC_TIMEOUT,
                 poll_interval: float = 1.0,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 now_fn: Callable[[], float] = time.monotonic,
                 poll_hook: Optional[Callable[[str], None]] = None) -> None:
        self.offline = offline if offline is not None else ex.is_offline()
        self.state = state or build_state_client(offline=self.offline)
        self.notifier = notifier or build_notifier(offline=self.offline)
        self.allowlist = allowlist if allowlist is not None else ex.load_allowlist()
        self.db_path = db_path
        self.approval_timeout = approval_timeout
        self.default_exec_timeout = default_exec_timeout
        self.poll_interval = poll_interval
        self._sleep_fn = sleep_fn
        self._now_fn = now_fn
        # Test seam: called with run_id on each approval-poll iteration so a test
        # can inject an approval/denial without a second process.
        self._poll_hook = poll_hook

    # -- public API ----------------------------------------------------------

    def exec_command(self, command: str, args: Optional[list[str]] = None,
                     cwd: Optional[str] = None, triggered_by: str = "eva",
                     timeout: Optional[int] = None,
                     approval_timeout: Optional[float] = None) -> dict:
        """Run an allowlisted command now, or gate a non-allowlisted one. NEVER raises."""
        try:
            return self._exec_command(command, args, cwd, triggered_by,
                                      timeout, approval_timeout)
        except Exception as exc:  # noqa: BLE001 — service must never crash
            logger.exception("local-exec exec_command crashed; continuing")
            return {"ok": False, "exit_code": -1, "stdout": "",
                    "stderr": f"{type(exc).__name__}: {exc}",
                    "duration": 0.0, "masked": False, "status": store.STATUS_FAILED,
                    "error": f"{type(exc).__name__}: {exc}"}

    def _exec_command(self, command, args, cwd, triggered_by, timeout,
                      approval_timeout) -> dict:
        args = list(args or [])
        argv = [command, *args]
        exec_timeout = timeout or self.default_exec_timeout
        rule = ex.match_allowlist(argv, cwd, self.allowlist)

        if rule is not None:
            return self._run_and_audit(
                argv, cwd, triggered_by, exec_timeout,
                approved_status=store.STATUS_ALLOWLISTED, rule=rule.get("name", ""))

        return self._gate(argv, cwd, triggered_by, exec_timeout,
                          approval_timeout or self.approval_timeout)

    def approve(self, run_id: str, approved: bool = True,
                actor: str = "founder") -> dict:
        """Approve/deny a pending run. The waiting exec call then runs it (approve)."""
        run = store.get_run(run_id, path=self.db_path)
        if not run:
            return {"ok": False, "error": f"run {run_id} not found"}
        if run["status"] != store.STATUS_PENDING:
            return {"ok": False, "noop": True, "run_id": run_id,
                    "status": run["status"],
                    "error": f"run already resolved: {run['status']}"}
        new_status = store.STATUS_APPROVED if approved else store.STATUS_DENIED
        store.update_run(run_id, {"status": new_status, "triggered_by": actor},
                         path=self.db_path)
        return {"ok": True, "run_id": run_id, "status": new_status}

    def status(self) -> dict:
        counts = store.count_by_status(path=self.db_path)
        return {
            "module": "eva-local-exec",
            "offline": self.offline,
            "bind": "127.0.0.1:8790 (loopback-only)",
            "allowlist_path": str(ex.ALLOWLIST_PATH),
            "allowlist": [r.get("name") for r in self.allowlist],
            "allowlist_count": len(self.allowlist),
            "approval_timeout_seconds": self.approval_timeout,
            "runs_by_status": counts,
            "runs_total": sum(counts.values()),
        }

    def history(self, limit: int = 20) -> dict:
        items = store.list_runs(limit=limit, path=self.db_path)
        return {"count": len(items), "items": items}

    # -- internals -----------------------------------------------------------

    def _run_and_audit(self, argv, cwd, triggered_by, exec_timeout,
                       *, approved_status, rule="", run_id=None) -> dict:
        """Execute argv, mask, then create/update the audit row + emit."""
        result = ex.run_command(argv[0], argv[1:], cwd=cwd, timeout=exec_timeout)
        masked_argv, arg_masked = ex.mask_argv(argv)
        masked = bool(result.get("masked")) or arg_masked
        status = approved_status if result.get("ok") else store.STATUS_FAILED

        fields = dict(
            command=masked_argv[0], args=masked_argv[1:], cwd=cwd or "",
            exit_code=result.get("exit_code"),
            stdout_masked=result.get("stdout", ""),
            stderr_masked=result.get("stderr", ""),
            duration=result.get("duration", 0.0),
            status=status, triggered_by=triggered_by, rule=rule, masked=masked,
        )
        if run_id is None:
            run = store.create_run(path=self.db_path, **fields)
        else:
            run = store.update_run(run_id, fields, path=self.db_path)

        event = "local_exec_failed" if status == store.STATUS_FAILED else (
            "local_exec_approved" if approved_status == store.STATUS_APPROVED
            else "local_exec_run")
        self._emit(event,
                   f"{event}: {masked_argv[0]} (exit {result.get('exit_code')}, "
                   f"{status})", run["id"], _run_payload(run, rule))
        return _response(run, result, rule=rule)

    def _gate(self, argv, cwd, triggered_by, exec_timeout, approval_timeout) -> dict:
        """Non-allowlisted → pending, notify, wait, then run/deny/expire."""
        masked_argv, arg_masked = ex.mask_argv(argv)
        run = store.create_run(
            path=self.db_path, command=masked_argv[0], args=masked_argv[1:],
            cwd=cwd or "", status=store.STATUS_PENDING, triggered_by=triggered_by,
            masked=arg_masked, expires_at=_expires_iso(approval_timeout))
        run_id = run["id"]

        notify = self.notifier.notify({**run, "args": masked_argv[1:]})
        self._emit("local_exec_blocked",
                   f"local_exec_blocked: {masked_argv[0]} not allowlisted — "
                   f"awaiting approval ({run_id})",
                   run_id, {**_run_payload(run, ""),
                            "approval_link": approval_link(run_id),
                            "notify": notify})

        resolved = self._await_approval(run_id, approval_timeout)

        if resolved == store.STATUS_APPROVED:
            # Run the ORIGINAL (unmasked) argv held in memory — no raw secret was
            # ever persisted, but we still need it to actually execute.
            return self._run_and_audit(
                argv, cwd, triggered_by, exec_timeout,
                approved_status=store.STATUS_APPROVED, rule="approved",
                run_id=run_id)

        if resolved == store.STATUS_DENIED:
            run = store.get_run(run_id, path=self.db_path)
            self._emit("local_exec_denied",
                       f"local_exec_denied: {masked_argv[0]} denied ({run_id})",
                       run_id, _run_payload(run, ""))
            return _response(run, {"ok": False, "exit_code": None, "stdout": "",
                                   "stderr": "denied — not executed",
                                   "duration": 0.0, "masked": arg_masked})

        # timeout → expire
        run = store.update_run(run_id, {"status": store.STATUS_EXPIRED},
                               path=self.db_path)
        self._emit("local_exec_expired",
                   f"local_exec_expired: {masked_argv[0]} not approved within "
                   f"{approval_timeout}s ({run_id})",
                   run_id, _run_payload(run, ""))
        return _response(run, {"ok": False, "exit_code": None, "stdout": "",
                               "stderr": f"approval timed out after {approval_timeout}s",
                               "duration": 0.0, "masked": arg_masked})

    def _await_approval(self, run_id: str, timeout: float) -> Optional[str]:
        """Poll the store until the run is approved/denied or the window lapses."""
        deadline = self._now_fn() + max(0.0, timeout)
        while self._now_fn() < deadline:
            if self._poll_hook is not None:
                self._poll_hook(run_id)
            run = store.get_run(run_id, path=self.db_path)
            if run and run["status"] in (store.STATUS_APPROVED, store.STATUS_DENIED):
                return run["status"]
            self._sleep_fn(self.poll_interval)
        return None

    def _emit(self, event_type: str, summary: str, run_id: str, payload: dict) -> None:
        """Best-effort eva-state emit; a ledger outage must never break a run."""
        try:
            self.state.emit(event_type=event_type, summary=summary,
                            entity_id=f"local_exec:{run_id}", payload=payload)
        except Exception:  # noqa: BLE001
            logger.exception("local-exec: state emit failed (ignored)")


def _run_payload(run: dict, rule: str) -> dict:
    return {"run_id": run.get("id"), "command": run.get("command"),
            "args": run.get("args"), "cwd": run.get("cwd"),
            "status": run.get("status"), "exit_code": run.get("exit_code"),
            "duration": run.get("duration"), "masked": run.get("masked"),
            "rule": rule or run.get("rule", "")}


def _response(run: dict, result: dict, rule: str = "") -> dict:
    return {
        "ok": bool(result.get("ok")),
        "exit_code": result.get("exit_code"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "duration": result.get("duration", 0.0),
        "masked": bool(result.get("masked")) or bool(run.get("masked")),
        "status": run.get("status"),
        "run_id": run.get("id"),
        "rule": rule or run.get("rule", ""),
    }


__all__ = ["LocalExecService", "DEFAULT_APPROVAL_TIMEOUT"]
