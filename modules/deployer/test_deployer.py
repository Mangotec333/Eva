"""
EVA Deployer — offline test suite (fake git/gh, fake launcher, fake in-flight
gate, stub ledger, zero network). Nothing real is EVER pulled or restarted: git
is a deterministic fake, the launcher is a fake that only records calls, the
in-flight gate is a fake, and the state client is a stub.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module runs:

  python modules/deployer/test_deployer.py
  (or)  cd modules/deployer && python test_deployer.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EVA_DEPLOYER_OFFLINE"] = "1"  # sandbox default; nothing real fires

import deployer as dep
from loop import DeployerLoop
from service import DeployerService
from state_client import StubStateLedgerClient

# A canonical module→service map so file→service mapping is deterministic in
# tests regardless of the host launcher.
MAP = {
    "social-scheduler": "social_scheduler",
    "triage-brain": "diracatron",
    "deployer": "deployer",
    "channels": "channels",
}


# ---------------------------------------------------------------------------
# Fakes (test doubles — never a real transport)
# ---------------------------------------------------------------------------

class FakeGit:
    """Deterministic git/gh double. Drives every branch of the deploy logic."""

    def __init__(self, *, local="aaaaaaa", remote="bbbbbbb",
                 pull=None, changed=None):
        self._local = local
        self._remote = remote
        self._pull = pull
        self._changed = changed or []
        self.pulled = 0
        self.fetched = 0

    def current_sha(self):
        return self._local

    def remote_sha(self):
        return self._remote

    def fetch(self):
        self.fetched += 1
        return {"ok": True, "output": ""}

    def pull_ff_only(self):
        self.pulled += 1
        if self._pull is not None:
            # simulate a successful ff by advancing local to remote
            if self._pull.get("ok"):
                self._local = self._pull.get("new_sha", self._remote)
            return self._pull
        old, new = self._local, self._remote
        self._local = new
        return {"ok": True, "conflict": False, "old_sha": old, "new_sha": new}

    def changed_files(self, old, new):
        return list(self._changed)


class FakeLauncher:
    """Records restart calls; never touches a real process."""

    def __init__(self, ok=True):
        self.ok = ok
        self.restarted = []

    def restart(self, service):
        self.restarted.append(service)
        return {"ok": self.ok, "service": service}


class FakeGate:
    """In-flight gate double: busy for the first ``busy_ticks`` checks."""

    def __init__(self, busy_ticks=0):
        self.busy_ticks = busy_ticks
        self.checks = 0

    def is_busy(self):
        self.checks += 1
        busy = self.checks <= self.busy_ticks
        return {"busy": busy, "locks": (["x.lock"] if busy else [])}


def _svc(git, *, launcher=None, gate=None, state=None, module_map=None):
    """Build a live-wired service (offline=False) with all seams injected."""
    return DeployerService(
        offline=False, git=git,
        launcher=launcher or FakeLauncher(),
        gate=gate or FakeGate(busy_ticks=0),
        state=state or StubStateLedgerClient(),
        module_map=module_map or MAP,
        restart_backoff=0.0, restart_max_attempts=4,
        sleep_fn=lambda s: None)


# ---------------------------------------------------------------------------
# poll interval — 5h default + env override
# ---------------------------------------------------------------------------

def test_poll_interval_default_is_five_hours():
    os.environ.pop("EVA_DEPLOYER_POLL_INTERVAL_SECONDS", None)
    assert dep.poll_interval_seconds() == 18000

def test_poll_interval_env_override():
    os.environ["EVA_DEPLOYER_POLL_INTERVAL_SECONDS"] = "60"
    try:
        assert dep.poll_interval_seconds() == 60
    finally:
        os.environ.pop("EVA_DEPLOYER_POLL_INTERVAL_SECONDS", None)

def test_poll_interval_ignores_garbage():
    os.environ["EVA_DEPLOYER_POLL_INTERVAL_SECONDS"] = "not-a-number"
    try:
        assert dep.poll_interval_seconds() == 18000
    finally:
        os.environ.pop("EVA_DEPLOYER_POLL_INTERVAL_SECONDS", None)


# ---------------------------------------------------------------------------
# map_files_to_services — pure diff → affected services
# ---------------------------------------------------------------------------

def test_map_files_to_services_maps_module_dirs():
    files = ["modules/social-scheduler/service.py",
             "modules/social-scheduler/loop.py",
             "modules/triage-brain/main.py"]
    assert dep.map_files_to_services(files, MAP) == ["diracatron", "social_scheduler"]

def test_map_files_ignores_non_module_and_unknown():
    files = ["README.md", "eva-start.sh", "modules/unknown-mod/x.py",
             "docs/notes.md"]
    assert dep.map_files_to_services(files, MAP) == []

def test_map_files_dedupes_same_service():
    files = ["modules/channels/a.py", "modules/channels/b.py"]
    assert dep.map_files_to_services(files, MAP) == ["channels"]

def test_default_module_map_has_known_services():
    mm = dep.default_module_map()
    # fallback (or parsed) always includes the core social-scheduler + deployer
    assert mm.get("social-scheduler") == "social_scheduler"
    assert mm.get("deployer") == "deployer"


# ---------------------------------------------------------------------------
# wait_until_free — bounded in-flight gating
# ---------------------------------------------------------------------------

def test_wait_free_immediately():
    res = dep.wait_until_free(FakeGate(busy_ticks=0), sleep_fn=lambda s: None)
    assert res["free"] is True and res["attempts"] == 1

def test_wait_free_after_busy_then_clears():
    res = dep.wait_until_free(FakeGate(busy_ticks=2), max_attempts=5,
                              backoff=0.0, sleep_fn=lambda s: None)
    assert res["free"] is True and res["attempts"] == 3

def test_wait_times_out_when_always_busy():
    res = dep.wait_until_free(FakeGate(busy_ticks=999), max_attempts=3,
                              backoff=0.0, sleep_fn=lambda s: None)
    assert res["free"] is False and res["attempts"] == 3


# ---------------------------------------------------------------------------
# service.check — offline no-op, up-to-date, check failure
# ---------------------------------------------------------------------------

def test_offline_check_is_noop():
    svc = DeployerService(offline=True, state=StubStateLedgerClient())
    res = svc.check()
    assert res["action"] == "noop_offline" and res["ok"] is True
    assert svc.git is None and svc.launcher is None and svc.gate is None

def test_up_to_date_when_local_equals_remote():
    git = FakeGit(local="same", remote="same")
    svc = _svc(git)
    res = svc.check()
    assert res["action"] == "up_to_date" and res["ok"] is True
    assert git.pulled == 0  # never pulled when already current

def test_check_failed_when_remote_sha_unresolved():
    git = FakeGit(local="aaa", remote="")
    state = StubStateLedgerClient()
    svc = _svc(git, state=state)
    res = svc.check()
    assert res["action"] == "check_failed" and res["ok"] is False
    assert git.pulled == 0
    assert any(e["event_type"] == "deploy_check_failed" for e in state.events)


# ---------------------------------------------------------------------------
# service.check — the happy self-deploy path
# ---------------------------------------------------------------------------

def test_deploy_applied_restarts_only_changed_services():
    git = FakeGit(local="old1234", remote="new5678",
                  pull={"ok": True, "conflict": False,
                        "old_sha": "old1234", "new_sha": "new5678"},
                  changed=["modules/social-scheduler/loop.py", "README.md"])
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check()
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert res["old_sha"] == "old1234" and res["new_sha"] == "new5678"
    assert res["services"] == ["social_scheduler"]
    assert launcher.restarted == ["social_scheduler"]  # README.md → no restart
    assert any(e["event_type"] == "deploy_applied" for e in state.events)

def test_deploy_with_no_service_changes_restarts_nothing():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False,
                        "old_sha": "old", "new_sha": "new"},
                  changed=["README.md", "SYSTEM_MAP.md"])
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher)
    res = svc.check()
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert res["services"] == [] and launcher.restarted == []


# ---------------------------------------------------------------------------
# SAFETY — conflict / non-fast-forward NEVER restarts anything
# ---------------------------------------------------------------------------

def test_conflict_aborts_and_never_restarts():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": False, "conflict": True, "old_sha": "old",
                        "new_sha": "old", "error": "Not possible to fast-forward"})
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check()
    assert res["action"] == "deploy_skipped_conflict" and res["ok"] is False
    assert launcher.restarted == []  # NOTHING restarted on conflict
    assert any(e["event_type"] == "deploy_skipped_conflict" for e in state.events)

def test_pull_failure_emits_deploy_failed_without_restart():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": False, "conflict": False, "old_sha": "old",
                        "new_sha": "old", "error": "fetch failed: network"})
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check()
    assert res["action"] == "deploy_failed" and res["ok"] is False
    assert launcher.restarted == []
    assert any(e["event_type"] == "deploy_failed" for e in state.events)


# ---------------------------------------------------------------------------
# SAFETY — gated on no in-flight work
# ---------------------------------------------------------------------------

def test_restart_waits_for_inflight_to_clear():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old",
                        "new_sha": "new"},
                  changed=["modules/social-scheduler/loop.py"])
    gate = FakeGate(busy_ticks=2)  # busy for 2 checks, then free
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher, gate=gate)
    res = svc.check()
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert launcher.restarted == ["social_scheduler"]  # restarted once free
    assert res["restarts"][0]["wait"]["attempts"] == 3

def test_restart_skipped_when_inflight_never_clears():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old",
                        "new_sha": "new"},
                  changed=["modules/social-scheduler/loop.py"])
    gate = FakeGate(busy_ticks=999)  # always busy
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher, gate=gate)
    res = svc.check()
    # bounded wait times out → we DO NOT kill a busy service
    assert launcher.restarted == []
    assert res["restarts"][0]["reason"] == "in_flight_timeout"
    assert res["action"] == "deploy_failed" and res["ok"] is False


# ---------------------------------------------------------------------------
# resilience — check() NEVER raises
# ---------------------------------------------------------------------------

def test_check_survives_git_exception():
    class BoomGit(FakeGit):
        def current_sha(self):
            raise RuntimeError("git blew up")

    state = StubStateLedgerClient()
    svc = _svc(BoomGit(), state=state)
    res = svc.check()  # must NOT raise
    assert res["action"] == "error" and res["ok"] is False
    assert "RuntimeError" in res["error"]

def test_restart_failure_reports_deploy_failed():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old",
                        "new_sha": "new"},
                  changed=["modules/channels/x.py"])
    launcher = FakeLauncher(ok=False)  # restart itself fails
    svc = _svc(git, launcher=launcher)
    res = svc.check()
    assert launcher.restarted == ["channels"]  # attempted
    assert res["action"] == "deploy_failed" and res["ok"] is False


# ---------------------------------------------------------------------------
# status / history
# ---------------------------------------------------------------------------

def test_status_reports_offline_and_interval():
    svc = DeployerService(offline=True, state=StubStateLedgerClient())
    st = svc.status()
    assert st["offline"] is True
    assert st["repo"] == dep.REPO and st["branch"] == dep.BRANCH
    assert st["poll_interval_seconds"] == 18000

def test_history_is_newest_first_and_bounded():
    git = FakeGit(local="same", remote="same")
    svc = _svc(git)
    for _ in range(3):
        svc.check()
    hist = svc.history(limit=2)
    assert hist["count"] == 3
    assert len(hist["items"]) == 2
    assert all(it["action"] == "up_to_date" for it in hist["items"])


# ---------------------------------------------------------------------------
# loop — offline no-op, fire, resilience
# ---------------------------------------------------------------------------

class FakeLoopService:
    def __init__(self, offline=False, raise_on_check=False):
        self.offline = offline
        self.raise_on_check = raise_on_check
        self.checks = 0

    def check(self):
        self.checks += 1
        if self.raise_on_check:
            raise RuntimeError("boom")
        return {"ok": True, "action": "up_to_date"}


def test_loop_offline_start_is_noop():
    loop = DeployerLoop(FakeLoopService(offline=True))
    assert loop.start() is False
    assert loop.is_running() is False
    out = loop.fire()
    assert out["fired"] is False and out.get("offline") is True

def test_loop_fire_runs_check():
    svc = FakeLoopService(offline=False)
    loop = DeployerLoop(svc, offline=False, interval=1.0)
    out = loop.fire()
    assert svc.checks == 1 and out["fired"] is True and out["action"] == "up_to_date"

def test_loop_fire_survives_check_exception():
    svc = FakeLoopService(offline=False, raise_on_check=True)
    loop = DeployerLoop(svc, offline=False, interval=1.0)
    out = loop.fire()  # must NOT raise
    assert out["ok"] is False and out["fired"] is False
    assert "RuntimeError" in out["error"]

def test_loop_body_keeps_looping_through_failures():
    svc = FakeLoopService(offline=False, raise_on_check=True)
    calls = {"n": 0}
    loop = DeployerLoop(svc, offline=False, interval=1.0, sleep_fn=lambda s: None)

    def sleeper(secs):
        calls["n"] += 1
        if calls["n"] >= 3:
            loop._stop.set()

    loop._sleep_fn = sleeper
    loop._run_forever()  # terminates via _stop
    assert calls["n"] >= 3
    assert len(loop.fires) >= 2  # multiple ticks fired despite failures


# ---------------------------------------------------------------------------
# no hardcoded GitHub token anywhere in the module
# ---------------------------------------------------------------------------

def test_no_hardcoded_github_token():
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in ("deployer.py", "service.py", "loop.py", "main.py",
               "cli.py", "state_client.py"):
        with open(os.path.join(here, fn), encoding="utf-8") as f:
            content = f.read()
        assert "ghp_" not in content, f"leaked GitHub token in {fn}"
        assert "github_pat_" not in content, f"leaked GitHub PAT in {fn}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {t.__name__}")
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
