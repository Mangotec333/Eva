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

import json
import logging
import os
import time
from collections import deque
from typing import Callable, Optional

import deployer as dep
import store
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("deployer.service")

HISTORY_MAX = 100


class DeployerService:
    def __init__(self, *,
                 targets: Optional[list[dict]] = None,
                 state: Optional[StateLedgerClient] = None,
                 git: Optional[dep.GitClient] = None,
                 git_factory: Optional[Callable[[dict], dep.GitClient]] = None,
                 launcher: Optional[dep.LauncherClient] = None,
                 gate: Optional[dep.InFlightGate] = None,
                 vercel: Optional[dep.VercelClient] = None,
                 module_map: Optional[dict[str, str]] = None,
                 offline: Optional[bool] = None,
                 require_approval: Optional[bool] = None,
                 db_path: str = store.DB_PATH,
                 restart_max_attempts: int = 12,
                 restart_backoff: float = 5.0,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_DEPLOYER_OFFLINE") == "1")
        # A self-deploy restarts a live Eva / ships prod, so it is gated behind
        # explicit approval by default (opt out only for tests / trusted autos).
        self.require_approval = require_approval if require_approval is not None \
            else (os.environ.get("EVA_DEPLOYER_REQUIRE_APPROVAL", "1") != "0")
        self.db_path = db_path
        store.init_db(self.db_path)
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
        self.module_map = module_map
        self.restart_max_attempts = restart_max_attempts
        self.restart_backoff = restart_backoff
        self._sleep_fn = sleep_fn
        self._history: deque[dict] = deque(maxlen=HISTORY_MAX)
        self._last_check_at: Optional[str] = None

    # -- introspection -------------------------------------------------------

    def status(self) -> dict:
        last = self._history[-1] if self._history else None
        return {
            "module": "eva-deployer",
            "offline": self.offline,
            "require_approval": self.require_approval,
            "pending_deploys": len(store.list_requests(status=store.STATUS_PENDING,
                                                       path=self.db_path)),
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

        # remote is ahead → gate on explicit approval before doing anything
        # irreversible (restarting a live Eva / shipping prod).
        if self.require_approval:
            return self._gate_deploy(target, local, remote)

        return self._execute_deploy(target, git, local, remote)

    def _execute_deploy(self, target: dict, git: dep.GitClient,
                        local: str, remote: str) -> dict:
        """Run the target's actual deploy action (post-approval / ungated)."""
        action = target.get("action", dep.ACTION_PULL_AND_RESTART)
        if action == dep.ACTION_VERCEL_PROD:
            return self._deploy_vercel(target, git, local, remote)
        return self._deploy_pull_and_restart(target, git, local, remote)

    # -- approve-then-deploy gate --------------------------------------------

    def _gate_deploy(self, target: dict, local: str, remote: str) -> dict:
        """Record a pending deploy request instead of deploying. Idempotent per
        target+remote SHA so repeated polls don't stack duplicates."""
        name = target.get("name", "?")
        action = target.get("action", dep.ACTION_PULL_AND_RESTART)
        existing = store.find_open_request(target=name, remote_sha=remote,
                                           path=self.db_path)
        request = existing or store.create_request(
            target=name, action=action, local_sha=local, remote_sha=remote,
            path=self.db_path)
        out = {"target": name, "action": "deploy_pending_approval", "ok": True,
               "request_id": request["id"], "status": request["status"],
               "local_sha": local, "remote_sha": remote,
               "deploy_action": action}
        if existing is None:
            self._emit("deploy_pending_approval",
                       f"[{name}] update {local[:7]}→{remote[:7]} awaiting approval "
                       f"(request {request['id']}); nothing deployed until approved",
                       target, out)
        return out

    def approve_deploy(self, request_id: str, *, actor: str = "launcher",
                       via: str = "endpoint") -> dict:
        """Approve a pending deploy request and execute it. Idempotent."""
        request = store.get_request(request_id, path=self.db_path)
        if not request:
            return {"ok": False, "error": f"deploy request {request_id} not found"}
        if request["status"] == store.STATUS_DEPLOYED:
            return {"ok": True, "noop": True, "request": request,
                    "reason": "already deployed"}
        if request["status"] == store.STATUS_REJECTED:
            return {"ok": False, "error": "deploy request was rejected",
                    "request": request}

        target = next((t for t in self.targets
                       if t.get("name") == request["target"]), None)
        if target is None:
            return {"ok": False,
                    "error": f"unknown target {request['target']}", "request": request}

        request = store.update_request(request_id, {
            "status": store.STATUS_APPROVED, "approval_actor": actor,
            "approval_via": via, "approved_at": store._now(),
        }, path=self.db_path)

        git = self._git_factory(target) if self._git_factory is not None else None
        if self.offline or git is None:
            self._emit("deploy_approved",
                       f"[{request['target']}] deploy approved by {actor} "
                       f"(offline — not executed)", target, {"request": request})
            return {"ok": True, "offline": True, "status": store.STATUS_APPROVED,
                    "request": request}

        local, remote = git.current_sha(), git.remote_sha()
        self._emit("deploy_approved",
                   f"[{request['target']}] deploy approved by {actor}; executing",
                   target, {"request_id": request_id})
        result = self._execute_deploy(target, git, local, remote)
        status = store.STATUS_DEPLOYED if result.get("ok") else store.STATUS_FAILED
        request = store.update_request(
            request_id, {"status": status, "result": json.dumps(result, default=str)},
            path=self.db_path)
        return {"ok": bool(result.get("ok")), "status": status,
                "request": request, "result": result}

    def reject_deploy(self, request_id: str, *, actor: str = "launcher") -> dict:
        request = store.get_request(request_id, path=self.db_path)
        if not request:
            return {"ok": False, "error": f"deploy request {request_id} not found"}
        if request["status"] == store.STATUS_DEPLOYED:
            return {"ok": False, "error": "already deployed — cannot reject",
                    "request": request}
        request = store.update_request(
            request_id, {"status": store.STATUS_REJECTED, "approval_actor": actor},
            path=self.db_path)
        target = next((t for t in self.targets
                       if t.get("name") == request["target"]), {"name": request["target"]})
        self._emit("deploy_rejected",
                   f"[{request['target']}] deploy request {request_id} rejected by "
                   f"{actor}. Not deployed.", target, {"request_id": request_id})
        return {"ok": True, "status": store.STATUS_REJECTED, "request": request}

    def list_pending_deploys(self, status: Optional[str] = None) -> dict:
        return {"requests": store.list_requests(status=status, path=self.db_path)}

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

        if self.vercel is None:
            out = {"target": name, "action": "deploy_landing_failed", "ok": False,
                   "old_sha": old_sha, "new_sha": new_sha, "vercel": False,
                   "error": "no vercel client"}
            self._emit("deploy_landing_failed",
                       f"[{name}] no vercel client wired", target, out)
            return out

        res = self.vercel.deploy_prod(path=target["path"], token=dep.vercel_token())
        ok = bool(res.get("ok"))
        out = {
            "target": name,
            "action": "deploy_landing_applied" if ok else "deploy_landing_failed",
            "ok": ok, "old_sha": old_sha, "new_sha": new_sha,
            "vercel": ok, "url": res.get("url", ""), "vercel_result": res,
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


__all__ = ["DeployerService", "HISTORY_MAX"]
