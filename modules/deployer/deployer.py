"""
EVA Deployer — the CI/CD self-update core (poll → safe pull → diff → gated
restart).

Eva keeps herself current: a background loop polls GitHub for new commits on
``main`` every 5 hours and, when the remote is ahead, fast-forwards the local
checkout and gracefully restarts only the Eva services whose module code
changed. **Safety is paramount** — this auto-restarts a *running* Eva, so every
guardrail here exists to never break a live system:

  * **Fast-forward ONLY.** ``git pull --ff-only``. Any conflict / non-fast-forward
    aborts the deploy, logs ``deploy_skipped_conflict``, restarts nothing, and the
    loop keeps going. We never merge, never rebase, never force.
  * **Restart only what changed.** ``git diff --name-only old..new`` maps changed
    files to launcher SERVICES entries; untouched services are left alone.
  * **Gated on no in-flight work.** Before restarting a service we wait (bounded
    retries) until nothing is mid-action, so we never kill a service while it is
    publishing / dispatching / gating.
  * **Resilient.** Every step is wrapped; an error is caught, logged, emitted to
    eva-state, and the loop survives. The service never crashes.
  * **Offline-safe.** ``EVA_DEPLOYER_OFFLINE=1`` → every real git/gh/launcher call
    is skipped; a check is a pure no-op.

Scope: **Eva-repo self-update only** (git pull + restart changed Eva services).
The eva-landing / Vercel deploy is handled separately by native Vercel
auto-deploy and is intentionally out of scope here.

Every network / process seam (git, launcher restart, in-flight gate, clock) is
injected so the whole thing runs offline in tests and fires nothing real.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger("deployer")

REPO = os.environ.get("EVA_DEPLOYER_REPO", "Mangotec333/Eva")
BRANCH = os.environ.get("EVA_DEPLOYER_BRANCH", "main")
EVA_HOME = Path(os.environ.get("EVA_HOME", str(Path.home() / "Eva")))
LAUNCHER_URL = os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768")

DEFAULT_POLL_INTERVAL_SECONDS = 18000  # 5 hours


def poll_interval_seconds() -> int:
    """Loop cadence — 5h default, override via EVA_DEPLOYER_POLL_INTERVAL_SECONDS."""
    raw = os.environ.get("EVA_DEPLOYER_POLL_INTERVAL_SECONDS", "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# changed-files → affected launcher services (pure)
# ---------------------------------------------------------------------------

_FALLBACK_MODULE_MAP = {
    "logger": "logger",
    "deal-scout": "deal_scout",
    "content-engine": "content_engine",
    "channels": "channels",
    "knowledge": "knowledge",
    "voice": "voice",
    "triage-brain": "diracatron",
    "finance-tracker": "treasurer",
    "social-scheduler": "social_scheduler",
    "deployer": "deployer",
}


def default_module_map() -> dict[str, str]:
    """Map ``modules/<dir>`` → launcher SERVICES key.

    Reuses the launcher's own SERVICES table (single source of truth for what
    runs and how) by parsing each entry's ``cmd`` for its module directory. If
    the launcher can't be imported (missing FastAPI in the sandbox, etc.) we
    fall back to a static mirror so a diff can still be mapped offline.
    """
    launcher_path = EVA_HOME / "modules" / "launcher"
    try:
        import sys
        if str(launcher_path) not in sys.path:
            sys.path.insert(0, str(launcher_path))
        import eva_launcher  # noqa: PLC0415
        mapping: dict[str, str] = {}
        for key, info in eva_launcher.SERVICES.items():
            m = re.search(r"modules/([\w.-]+)", info.get("cmd", "") or "")
            if m:
                mapping[m.group(1)] = key
        mapping.setdefault("deployer", "deployer")
        if mapping:
            return mapping
    except Exception:  # noqa: BLE001 — sandbox / missing deps: use the fallback
        logger.debug("launcher SERVICES unavailable; using fallback module map")
    return dict(_FALLBACK_MODULE_MAP)


def map_files_to_services(files: list[str],
                          module_map: Optional[dict[str, str]] = None) -> list[str]:
    """Reduce a changed-file list to the set of launcher service keys to restart.

    A file at ``modules/<dir>/...`` maps to the service that runs ``<dir>``.
    Files outside ``modules/`` (root scripts, docs) map to nothing — they don't
    correspond to a restartable service. Order is stable (sorted) for tests.
    """
    mm = module_map if module_map is not None else default_module_map()
    hit: set[str] = set()
    for f in files:
        m = re.match(r"modules/([\w.-]+)/", f.strip())
        if m and m.group(1) in mm:
            hit.add(mm[m.group(1)])
    return sorted(hit)


# ---------------------------------------------------------------------------
# Git seam — real subprocess git/gh, injectable for tests
# ---------------------------------------------------------------------------

@runtime_checkable
class GitClient(Protocol):
    def current_sha(self) -> str: ...
    def remote_sha(self) -> str: ...
    def fetch(self) -> dict: ...
    def pull_ff_only(self) -> dict: ...
    def changed_files(self, old: str, new: str) -> list[str]: ...


class SubprocessGitClient:
    """Live git/gh client rooted at ``EVA_HOME``.

    ``pull_ff_only`` is a fetch + ``merge --ff-only`` so a non-fast-forward can
    NEVER mutate the working tree: git refuses and we report ``conflict``.
    """

    def __init__(self, repo_dir: Path = EVA_HOME, repo: str = REPO,
                 branch: str = BRANCH, timeout: float = 120.0) -> None:
        self.repo_dir = Path(repo_dir)
        self.repo = repo
        self.branch = branch
        self.timeout = timeout

    def _git(self, *args: str, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(self.repo_dir),
            capture_output=True, text=True, timeout=timeout or self.timeout)

    def current_sha(self) -> str:
        cp = self._git("rev-parse", "HEAD", timeout=15)
        return cp.stdout.strip() if cp.returncode == 0 else ""

    def remote_sha(self) -> str:
        """Prefer the GitHub API via gh (auth handled on the Mac); fall back to
        ``git ls-remote`` if gh is unavailable. Empty string on total failure."""
        try:
            cp = subprocess.run(
                ["gh", "api", f"repos/{self.repo}/commits/{self.branch}",
                 "--jq", ".sha"],
                cwd=str(self.repo_dir), capture_output=True, text=True, timeout=30)
            if cp.returncode == 0 and cp.stdout.strip():
                return cp.stdout.strip()
        except Exception:  # noqa: BLE001 — gh missing / not authed → ls-remote
            pass
        try:
            cp = self._git("ls-remote", "origin", self.branch, timeout=30)
            if cp.returncode == 0 and cp.stdout.strip():
                return cp.stdout.split()[0].strip()
        except Exception:  # noqa: BLE001
            pass
        return ""

    def fetch(self) -> dict:
        cp = self._git("fetch", "origin", self.branch)
        return {"ok": cp.returncode == 0, "output": (cp.stdout + cp.stderr).strip()}

    def pull_ff_only(self) -> dict:
        old = self.current_sha()
        fetched = self.fetch()
        if not fetched["ok"]:
            return {"ok": False, "conflict": False, "old_sha": old, "new_sha": old,
                    "error": f"fetch failed: {fetched['output']}"}
        cp = self._git("merge", "--ff-only", f"origin/{self.branch}")
        new = self.current_sha()
        if cp.returncode != 0:
            # non-fast-forward / divergence — git refused, tree is untouched
            return {"ok": False, "conflict": True, "old_sha": old, "new_sha": new,
                    "error": (cp.stdout + cp.stderr).strip()}
        return {"ok": True, "conflict": False, "old_sha": old, "new_sha": new,
                "output": (cp.stdout + cp.stderr).strip()}

    def changed_files(self, old: str, new: str) -> list[str]:
        if not old or not new or old == new:
            return []
        cp = self._git("diff", "--name-only", f"{old}..{new}", timeout=30)
        if cp.returncode != 0:
            return []
        return [ln.strip() for ln in cp.stdout.splitlines() if ln.strip()]


def build_git_client() -> GitClient:
    return SubprocessGitClient()


# ---------------------------------------------------------------------------
# Launcher seam — graceful restart of a single service
# ---------------------------------------------------------------------------

@runtime_checkable
class LauncherClient(Protocol):
    def restart(self, service: str) -> dict: ...


class HttpLauncherClient:
    """Restart a service via the launcher's own stop→start routes (:8768).

    The launcher owns the SERVICES table + restart mechanism; we drive it rather
    than duplicate process management. Restart = stop (SIGTERM by port) then
    start (relaunch its command)."""

    def __init__(self, base_url: str = LAUNCHER_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str) -> dict:
        import urllib.request
        req = urllib.request.Request(f"{self.base_url}{path}", data=b"", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                import json
                raw = resp.read().decode() or "{}"
                return {"ok": 200 <= resp.status < 300, **json.loads(raw)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def restart(self, service: str) -> dict:
        stop = self._post(f"/stop/{service}")
        start = self._post(f"/start/{service}")
        return {"ok": bool(start.get("ok")), "service": service,
                "stop": stop, "start": start}


def build_launcher_client() -> LauncherClient:
    return HttpLauncherClient()


# ---------------------------------------------------------------------------
# In-flight gate — never restart a service that is mid-action
# ---------------------------------------------------------------------------

@runtime_checkable
class InFlightGate(Protocol):
    def is_busy(self) -> dict: ...


class LockDirInFlightGate:
    """Best-effort in-flight detector via lock files.

    Agents that are mid-action (social-scheduler firing a slot, a gate awaiting
    approval, a dispatch in progress) drop a ``*.lock`` file in
    ``EVA_INFLIGHT_LOCK_DIR`` (default ``~/.eva/locks``). While any lock exists
    we consider Eva busy and hold the restart. No directory / no locks → free.
    """

    def __init__(self, lock_dir: Optional[Path] = None) -> None:
        self.lock_dir = Path(lock_dir) if lock_dir else Path(
            os.environ.get("EVA_INFLIGHT_LOCK_DIR", str(Path.home() / ".eva" / "locks")))

    def is_busy(self) -> dict:
        try:
            if not self.lock_dir.is_dir():
                return {"busy": False, "locks": []}
            locks = [p.name for p in self.lock_dir.glob("*.lock")]
            return {"busy": bool(locks), "locks": locks}
        except Exception as exc:  # noqa: BLE001 — never let a stat error block deploy
            logger.debug("in-flight gate check failed: %s", exc)
            return {"busy": False, "locks": [], "error": str(exc)}


def build_inflight_gate() -> InFlightGate:
    return LockDirInFlightGate()


def wait_until_free(gate: InFlightGate, *, max_attempts: int = 12,
                    backoff: float = 5.0,
                    sleep_fn: Callable[[float], None] = time.sleep) -> dict:
    """Block until the in-flight gate reports free, bounded by ``max_attempts``.

    Returns ``{"free": bool, "attempts": n, "last": <gate result>}``. On timeout
    ``free`` is False and the caller decides to skip that service's restart —
    we would rather leave a slightly-stale service running than kill it mid-task.
    """
    last: dict = {}
    for attempt in range(1, max_attempts + 1):
        last = gate.is_busy()
        if not last.get("busy"):
            return {"free": True, "attempts": attempt, "last": last}
        if attempt < max_attempts:
            sleep_fn(backoff)
    return {"free": False, "attempts": max_attempts, "last": last}


__all__ = [
    "poll_interval_seconds", "DEFAULT_POLL_INTERVAL_SECONDS",
    "default_module_map", "map_files_to_services",
    "GitClient", "SubprocessGitClient", "build_git_client",
    "LauncherClient", "HttpLauncherClient", "build_launcher_client",
    "InFlightGate", "LockDirInFlightGate", "build_inflight_gate", "wait_until_free",
    "REPO", "BRANCH", "EVA_HOME",
]
