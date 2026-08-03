"""
EVA Deployer — service layer (poll → per-target safe deploy → log).

Every 5-hour pass iterates ALL configured deploy targets and, per target's
``action``, does the safe thing:

  * ``pull_and_restart`` (the Eva repo) — fast-forward-only pull + graceful
    restart of ONLY the launcher services whose module code changed, gated on
    no in-flight work.
  * ``vercel_prod`` (the eva-landing repo) — fast-forward-only pull + native
    ``vercel --prod``. On any failure we abort + log + skip so a broken build
    never ships / never leaves the landing half-deployed.

Wires the ``deployer`` seams (per-target git, launcher, in-flight gate, vercel,
eva-state) and keeps a bounded in-memory history of every pass so
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
import store
from approve import ApprovalNotifier, approval_link, build_notifier
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("deployer.service")

HISTORY_MAX = 100
DEFAULT_APPROVAL_TIMEOUT = 600  # seconds to wait for one-tap landing approval


def _approval_timeout_default() -> float:
    """Landing-deploy approval window — 600s default, env-overridable."""
    raw = os.environ.get("EVA_DEPLOYER_APPROVAL_TIMEOUT", "").strip()
    if raw:
        try:
            val = float(raw)
            if val >= 0:
                return val
        except ValueError:
            pass
    return float(DEFAULT_APPROVAL_TIMEOUT)


class DeployerService:
    def __init__(self, *,
                 targets: Optional[list[dict]] = None,
                 state: Optional[StateLedgerClient] = None,
                 git: Optional[dep.GitClient] = None,
                 git_factory: Optional[Callable[[dict], dep.GitClient]] = None,
                 launcher: Optional[dep.LauncherClient] = None,
                 gate: Optional[dep.InFlightGate] = None,
                 vercel: Optional[dep.VercelClient] = None,
                 notifier: Optional[ApprovalNotifier] = None,
                 module_map: Optional[dict[str, str]] = None,
                 offline: Optional[bool] = None,
                 restart_max_attempts: int = 12,
                 restart_backoff: float = 5.0,
                 approval_timeout: Optional[float] = None,
                 approval_poll_interval: float = 1.0,
                 db_path: Optional[str] = None,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 now_fn: Callable[[], float] = time.monotonic,
                 poll_hook: Optional[Callable[[str], None]] = None) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_DEPLOYER_OFFLINE") == "1")
        self.targets = targets if targets is not None else dep.deploy_targets()
        self.state = state or build_state_client(offline=self.offline)
        # ``git`` (single client) is a convenience for single-target tests; it
        # wins for every target. Otherwise use the injected/real per-target
        # factory. Real transport is only built when live; offline leaves the
        # seams None so a check is provably a no-op.
        if git is not None:
            self._git_factory: Optional[Callable[[dict], dep.GitClient]] = lambda _t: git
        elif git_factory is not None:
            self._git_factory = git_factory
        else:
            self._git_factory = None if self.offline else dep.build_git_client_for
        self.launcher = launcher or (None if self.offline else dep.build_launcher_client())
        self.gate = gate or (None if self.offline else dep.build_inflight_gate())
        self.vercel = vercel or (None if self.offline else dep.build_vercel_client())
        # Landing-deploy approval notifier — a Stub whenever offline (never
        # touches Slack), the live Slack notifier otherwise. Mirrors local-exec.
        self.notifier = notifier or build_notifier(offline=self.offline)
        self.module_map = module_map
        self.restart_max_attempts = restart_max_attempts
        self.restart_backoff = restart_backoff
        self.approval_timeout = (approval_timeout if approval_timeout is not None
                                 else _approval_timeout_default())
        self.approval_poll_interval = approval_poll_interval
        self.db_path = db_path
        self._sleep_fn = sleep_fn
        self._now_fn = now_fn
        # Test seam: called with deploy_id on each approval-poll iteration so a
        # test can inject an approval/denial without a second process.
        self._poll_hook = poll_hook
        self._history: deque[dict] = deque(maxlen=HISTORY_MAX)
        self._last_check_at: Optional[str] = None

    # -- introspection -------------------------------------------------------

    def status(self) -> dict:
        last = self._history[-1] if self._history else None
        return {
            "module": "eva-deployer",
            "offline": self.offline,
            "poll_interval_seconds": dep.poll_interval_seconds(),
            "targets": [{"name": t.get("name"), "repo": t.get("repo"),
                         "path": t.get("path"), "branch": t.get("branch"),
                         "action": t.get("action")} for t in self.targets],
            "last_check_at": self._last_check_at,
            "last_result": last,
            "history_count": len(self._history),
        }

    def history(self, limit: int = 20) -> dict:
        items = list(self._history)[-max(1, limit):]
        return {"count": len(self._history), "items": list(reversed(items))}

    # -- the deploy pass -----------------------------------------------------

    def check(self) -> dict:
        """One pass over ALL deploy targets. NEVER raises."""
        self._last_check_at = _now_iso()
        results: list[dict] = []
        for target in self.targets:
            results.append(self.check_target(target))
        pass_result = {
            "action": "check",
            "ok": all(r.get("ok") for r in results) if results else True,
            "checked_at": self._last_check_at,
            "targets": results,
        }
        self._history.append(pass_result)
        return pass_result

    def check_target(self, target: dict) -> dict:
        """Poll one target and (maybe) safely deploy it. NEVER raises."""
        name = target.get("name", "?")
        try:
            result = self._check_target(target)
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.exception("deployer target %s crashed; continuing", name)
            result = {"target": name, "action": "error", "ok": False,
                      "error": f"{type(exc).__name__}: {exc}"}
            self._emit("deploy_failed", f"Deployer target {name} crashed: {exc}",
                       target, result)
        result.setdefault("target", name)
        return result

    def _check_target(self, target: dict) -> dict:
        name = target.get("name", "?")
        git = self._git_factory(target) if self._git_factory is not None else None
        if self.offline or git is None:
            return {"target": name, "action": "noop_offline", "ok": True,
                    "offline": True}

        local = git.current_sha()
        remote = git.remote_sha()
        if not remote:
            out = {"target": name, "action": "check_failed", "ok": False,
                   "local_sha": local,
                   "error": "could not resolve remote SHA (gh/ls-remote failed)"}
            self._emit("deploy_check_failed",
                       f"[{name}] could not resolve remote SHA", target, out)
            return out
        if local == remote:
            return {"target": name, "action": "up_to_date", "ok": True,
                    "local_sha": local, "remote_sha": remote}

        # remote is ahead → dispatch by the target's action
        action = target.get("action", dep.ACTION_PULL_AND_RESTART)
        if action == dep.ACTION_VERCEL_PROD:
            return self._deploy_vercel(target, git, local, remote)
        return self._deploy_pull_and_restart(target, git, local, remote)

    # -- action: pull + graceful restart (the Eva repo) ----------------------

    def _deploy_pull_and_restart(self, target: dict, git: dep.GitClient,
                                 local: str, remote: str) -> dict:
        name = target.get("name", "?")
        pull = git.pull_ff_only()
        old_sha, new_sha = pull.get("old_sha", local), pull.get("new_sha", local)

        if pull.get("conflict"):
            out = {"target": name, "action": "deploy_skipped_conflict", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "error": pull.get("error", "non-fast-forward")}
            self._emit("deploy_skipped_conflict",
                       f"[{name}] self-deploy aborted: non-fast-forward — kept running",
                       target, out)
            return out
        if not pull.get("ok"):
            out = {"target": name, "action": "deploy_failed", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "error": pull.get("error", "pull failed")}
            self._emit("deploy_failed", f"[{name}] pull failed: {out['error']}",
                       target, out)
            return out

        changed = git.changed_files(old_sha, new_sha)
        services = dep.map_files_to_services(changed, self.module_map)
        restarts = self._restart_services(services)

        all_ok = all(r.get("ok") for r in restarts)
        out = {
            "target": name,
            "action": "deploy_applied" if all_ok else "deploy_failed",
            "ok": all_ok, "old_sha": old_sha, "new_sha": new_sha,
            "changed_files": changed, "services": services, "restarts": restarts,
        }
        if all_ok:
            self._emit("deploy_applied",
                       f"[{name}] self-deployed {old_sha[:7]}→{new_sha[:7]}; "
                       f"restarted {len(services)} service(s): {', '.join(services) or 'none'}",
                       target, out)
        else:
            self._emit("deploy_failed",
                       f"[{name}] deployed {old_sha[:7]}→{new_sha[:7]} but a restart failed",
                       target, out)
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

    # -- action: vercel --prod (the eva-landing repo) ------------------------

    def _deploy_vercel(self, target: dict, git: dep.GitClient,
                       local: str, remote: str) -> dict:
        name = target.get("name", "?")
        pull = git.pull_ff_only()
        old_sha, new_sha = pull.get("old_sha", local), pull.get("new_sha", remote)

        # Any non-fast-forward / pull failure → abort + log + skip (never ship a
        # half-updated tree). Reported as deploy_landing_failed per spec.
        if pull.get("conflict") or not pull.get("ok"):
            out = {"target": name, "action": "deploy_landing_failed", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "vercel": False,
                   "error": pull.get("error",
                                     "non-fast-forward" if pull.get("conflict") else "pull failed")}
            self._emit("deploy_landing_failed",
                       f"[{name}] landing pull aborted; vercel NOT run: {out['error']}",
                       target, out)
            return out

        # Approval gate — a live-site deploy NEVER ships on its own. Record it as
        # pending, post a one-tap Slack request, and wait (bounded) for approval
        # via reply/reaction or POST /deployer/approve. Only on approve do we run
        # vercel; on deny/timeout the old version stays live.
        changed = git.changed_files(old_sha, new_sha)
        gate = self._await_landing_approval(target, old_sha, new_sha, remote, changed)
        deploy_id = gate["deploy_id"]

        if gate["status"] == store.STATUS_DENIED:
            out = {"target": name, "action": "deploy_landing_denied", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "vercel": False, "deploy_id": deploy_id,
                   "error": "denied — not shipped"}
            self._emit("deploy_landing_denied",
                       f"[{name}] landing deploy denied ({deploy_id}); "
                       f"vercel NOT run — old version stays live",
                       target, out)
            return out

        if gate["status"] != store.STATUS_APPROVED:
            # timeout / not approved within the window → expire, do not ship
            out = {"target": name, "action": "deploy_landing_expired", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "remote_sha": remote,
                   "vercel": False, "deploy_id": deploy_id,
                   "error": f"approval timed out after {self.approval_timeout}s"}
            self._emit("deploy_landing_expired",
                       f"[{name}] landing deploy not approved within "
                       f"{self.approval_timeout}s ({deploy_id}); vercel NOT run",
                       target, out)
            return out

        # approved → proceed with the existing vercel --prod flow unchanged
        if self.vercel is None:
            store.update_deploy(deploy_id, {"status": store.STATUS_FAILED},
                                db_path=self.db_path)
            out = {"target": name, "action": "deploy_landing_failed", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "vercel": False,
                   "deploy_id": deploy_id, "error": "no vercel client"}
            self._emit("deploy_landing_failed",
                       f"[{name}] no vercel client wired", target, out)
            return out

        res = self.vercel.deploy_prod(path=target["path"], token=dep.vercel_token())
        ok = bool(res.get("ok"))
        store.update_deploy(
            deploy_id,
            {"status": store.STATUS_APPLIED if ok else store.STATUS_FAILED},
            db_path=self.db_path)
        out = {
            "target": name,
            "action": "deploy_landing_applied" if ok else "deploy_landing_failed",
            "ok": ok, "old_sha": old_sha, "new_sha": new_sha,
            "vercel": ok, "url": res.get("url", ""), "vercel_result": res,
            "deploy_id": deploy_id,
        }
        if ok:
            self._emit("deploy_landing_applied",
                       f"[{name}] vercel --prod deployed {old_sha[:7]}→{new_sha[:7]}"
                       + (f" → {res.get('url')}" if res.get("url") else ""),
                       target, out)
        else:
            self._emit("deploy_landing_failed",
                       f"[{name}] vercel --prod failed: {res.get('error') or res.get('returncode')}",
                       target, out)
        return out

    def _await_landing_approval(self, target: dict, old_sha: str, new_sha: str,
                                remote: str, changed: list[str]) -> dict:
        """Record a pending landing deploy, notify, and wait (bounded) for approval.

        Returns ``{"deploy_id", "status"}`` where status is one of
        ``approved`` / ``denied`` / ``expired`` (``pending_approval`` never
        leaks out — a lapsed window is reported as ``expired``)."""
        name = target.get("name", "?")
        summary = _changed_summary(changed)
        deploy = store.create_deploy(
            target=name, repo=target.get("repo", ""), path=target.get("path", ""),
            old_sha=old_sha, new_sha=new_sha, changed_summary=summary,
            status=store.STATUS_PENDING_APPROVAL,
            expires_at=_expires_iso(self.approval_timeout), db_path=self.db_path)
        deploy_id = deploy["id"]

        notify = self.notifier.notify(deploy)
        self._emit("deploy_landing_pending",
                   f"[{name}] live-site deploy {old_sha[:7]}→{new_sha[:7]} "
                   f"awaiting approval ({deploy_id})",
                   target, {"deploy_id": deploy_id, "old_sha": old_sha,
                            "new_sha": new_sha, "changed_summary": summary,
                            "approval_link": approval_link(deploy_id),
                            "notify": notify})

        resolved = self._poll_for_approval(deploy_id, self.approval_timeout)
        if resolved in (store.STATUS_APPROVED, store.STATUS_DENIED):
            return {"deploy_id": deploy_id, "status": resolved}
        # window lapsed → expire in place
        store.update_deploy(deploy_id, {"status": store.STATUS_EXPIRED},
                            db_path=self.db_path)
        return {"deploy_id": deploy_id, "status": store.STATUS_EXPIRED}

    def _poll_for_approval(self, deploy_id: str, timeout: float) -> Optional[str]:
        """Poll the store until the deploy is approved/denied or the window lapses."""
        deadline = self._now_fn() + max(0.0, timeout)
        while self._now_fn() < deadline:
            if self._poll_hook is not None:
                self._poll_hook(deploy_id)
            deploy = store.get_deploy(deploy_id, db_path=self.db_path)
            if deploy and deploy["status"] in (
                    store.STATUS_APPROVED, store.STATUS_DENIED):
                return deploy["status"]
            self._sleep_fn(self.approval_poll_interval)
        return None

    def approve(self, deploy_id: str, approved: bool = True,
                actor: str = "founder") -> dict:
        """Approve/deny a pending landing deploy. The waiting deploy then ships (approve)."""
        deploy = store.get_deploy(deploy_id, db_path=self.db_path)
        if not deploy:
            return {"ok": False, "error": f"deploy {deploy_id} not found"}
        if deploy["status"] != store.STATUS_PENDING_APPROVAL:
            return {"ok": False, "noop": True, "deploy_id": deploy_id,
                    "status": deploy["status"],
                    "error": f"deploy already resolved: {deploy['status']}"}
        new_status = store.STATUS_APPROVED if approved else store.STATUS_DENIED
        store.update_deploy(deploy_id, {"status": new_status, "triggered_by": actor},
                            db_path=self.db_path)
        return {"ok": True, "deploy_id": deploy_id, "status": new_status}

    # -- eva-state -----------------------------------------------------------

    def _emit(self, event_type: str, summary: str, target: dict, payload: dict) -> None:
        """Best-effort eva-state emit; a ledger outage must not break a deploy."""
        try:
            self.state.emit(event_type=event_type, summary=summary,
                            entity_id=f"deployer:{target.get('name', '?')}",
                            payload=payload)
        except Exception:  # noqa: BLE001
            logger.exception("deployer: state emit failed (ignored)")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(seconds: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _changed_summary(changed: list[str], limit: int = 20) -> str:
    """A compact newline-joined changed-file list for the approval request."""
    files = [f for f in (changed or []) if f]
    if not files:
        return ""
    shown = files[:limit]
    extra = len(files) - len(shown)
    out = "\n".join(shown)
    if extra > 0:
        out += f"\n… (+{extra} more)"
    return out


__all__ = ["DeployerService", "HISTORY_MAX", "DEFAULT_APPROVAL_TIMEOUT"]
