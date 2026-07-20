"""
EVA Deployer — offline test suite (fake git/gh, fake launcher, fake in-flight
gate, fake vercel CLI, stub ledger, zero network). Nothing real is EVER pulled,
restarted, or deployed: git is a deterministic fake, the launcher/vercel only
record calls, the in-flight gate is a fake, and the state client is a stub.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module runs:

  python modules/deployer/test_deployer.py
  (or)  cd modules/deployer && python test_deployer.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EVA_DEPLOYER_OFFLINE"] = "1"  # sandbox default; nothing real fires

import deployer as dep
import store
from approve import StubApprovalNotifier
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

EVA_TARGET = {"name": "eva", "repo": "Mangotec333/Eva", "path": "/tmp/eva",
              "branch": "main", "action": "pull_and_restart"}
LANDING_TARGET = {"name": "eva-landing", "repo": "Mangotec333/eva-landing",
                  "path": "/tmp/eva-landing", "branch": "master",
                  "action": "vercel_prod"}


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


class FakeVercel:
    """Vercel CLI double: records deploy calls, never runs the real CLI."""

    def __init__(self, ok=True, url="https://eva-landing.vercel.app"):
        self.ok = ok
        self.url = url
        self.calls = []

    def deploy_prod(self, *, path, token=""):
        self.calls.append({"path": path, "token": token})
        if self.ok:
            return {"ok": True, "url": self.url, "returncode": 0}
        return {"ok": False, "returncode": 1, "error": "vercel exploded"}


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="deployer_", suffix=".db")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return path


def _clock():
    """A monotonically advancing fake clock (so timeouts are deterministic)."""
    state = {"t": 0.0}

    def now():
        state["t"] += 0.001
        return state["t"]
    return now


def _svc(git, *, target=EVA_TARGET, launcher=None, gate=None, state=None,
         vercel=None, notifier=None, module_map=None, approval_timeout=5.0):
    """Build a live-wired single-target service with all seams injected.

    Landing (vercel_prod) deploys are AUTO-APPROVED by default (a poll_hook that
    approves on the first wait iteration) so the existing landing tests — which
    assert vercel runs — pass unchanged. Gate-specific tests override
    ``svc._poll_hook`` / ``approval_timeout`` to exercise deny / expire / hold.
    """
    svc = DeployerService(
        offline=False, git=git, targets=[target],
        launcher=launcher or FakeLauncher(),
        gate=gate or FakeGate(busy_ticks=0),
        vercel=vercel or FakeVercel(),
        notifier=notifier or StubApprovalNotifier(),
        state=state or StubStateLedgerClient(),
        module_map=module_map or MAP,
        restart_backoff=0.0, restart_max_attempts=4,
        approval_timeout=approval_timeout, approval_poll_interval=0.0,
        db_path=_tmp_db(), sleep_fn=lambda s: None, now_fn=_clock())
    svc._poll_hook = lambda did: svc.approve(did, True, actor="founder")
    return svc


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
# deploy targets — configurable list (config-file primary → env → default)
# ---------------------------------------------------------------------------

def test_deploy_targets_default_has_both():
    # no config file, no env → built-in default (eva + eva-landing)
    old = dep.CHANNELS_CONFIG_PATH
    dep.CHANNELS_CONFIG_PATH = dep.Path("/nonexistent/eva/channels_config.json")
    os.environ.pop("EVA_DEPLOY_TARGETS", None)
    try:
        ts = dep.deploy_targets()
        names = [t["name"] for t in ts]
        assert names == ["eva", "eva-landing"]
        landing = [t for t in ts if t["name"] == "eva-landing"][0]
        assert landing["action"] == "vercel_prod" and landing["branch"] == "master"
        eva = [t for t in ts if t["name"] == "eva"][0]
        assert eva["action"] == "pull_and_restart"
    finally:
        dep.CHANNELS_CONFIG_PATH = old

def test_deploy_targets_config_file_is_primary():
    old = dep.CHANNELS_CONFIG_PATH
    fd, cfgpath = tempfile.mkstemp(prefix="dep_cfg_", suffix=".json")
    os.close(fd)
    with open(cfgpath, "w") as f:
        json.dump({"deploy_targets": [
            {"name": "only-landing", "repo": "x/y", "path": "~/z",
             "branch": "master", "action": "vercel_prod"}]}, f)
    dep.CHANNELS_CONFIG_PATH = dep.Path(cfgpath)
    os.environ["EVA_DEPLOY_TARGETS"] = json.dumps([{"name": "env", "repo": "e/e"}])
    try:
        ts = dep.deploy_targets()
        assert [t["name"] for t in ts] == ["only-landing"]  # file wins over env
        assert ts[0]["path"] == os.path.expanduser("~/z")   # ~ expanded
    finally:
        dep.CHANNELS_CONFIG_PATH = old
        os.environ.pop("EVA_DEPLOY_TARGETS", None)
        os.unlink(cfgpath)

def test_deploy_targets_env_fallback_when_no_config():
    old = dep.CHANNELS_CONFIG_PATH
    dep.CHANNELS_CONFIG_PATH = dep.Path("/nonexistent/eva/channels_config.json")
    os.environ["EVA_DEPLOY_TARGETS"] = json.dumps(
        [{"name": "envtgt", "repo": "e/e", "path": "/tmp/e", "action": "pull_and_restart"}])
    try:
        ts = dep.deploy_targets()
        assert [t["name"] for t in ts] == ["envtgt"]
    finally:
        dep.CHANNELS_CONFIG_PATH = old
        os.environ.pop("EVA_DEPLOY_TARGETS", None)


# ---------------------------------------------------------------------------
# vercel token — config-file primary, VERCEL_TOKEN env fallback
# ---------------------------------------------------------------------------

def test_vercel_token_config_primary_over_env():
    old = dep.CHANNELS_CONFIG_PATH
    fd, cfgpath = tempfile.mkstemp(prefix="dep_vcfg_", suffix=".json")
    os.close(fd)
    with open(cfgpath, "w") as f:
        json.dump({"vercel": {"token": "FILE_VTOKEN"}}, f)
    dep.CHANNELS_CONFIG_PATH = dep.Path(cfgpath)
    os.environ["VERCEL_TOKEN"] = "ENV_SHOULD_LOSE"
    try:
        assert dep.vercel_token() == "FILE_VTOKEN"
    finally:
        dep.CHANNELS_CONFIG_PATH = old
        os.environ.pop("VERCEL_TOKEN", None)
        os.unlink(cfgpath)

def test_vercel_token_env_fallback():
    old = dep.CHANNELS_CONFIG_PATH
    dep.CHANNELS_CONFIG_PATH = dep.Path("/nonexistent/eva/channels_config.json")
    os.environ["VERCEL_TOKEN"] = "ENV_VTOKEN"
    try:
        assert dep.vercel_token() == "ENV_VTOKEN"
    finally:
        dep.CHANNELS_CONFIG_PATH = old
        os.environ.pop("VERCEL_TOKEN", None)

def test_extract_vercel_url():
    out = "Inspect: ...\nProduction: https://eva-landing-abc.vercel.app [2s]"
    assert dep._extract_vercel_url(out) == "https://eva-landing-abc.vercel.app"
    assert dep._extract_vercel_url("no url here") == ""


# ---------------------------------------------------------------------------
# map_files_to_services — pure diff → affected services
# ---------------------------------------------------------------------------

def test_map_files_to_services_maps_module_dirs():
    files = ["modules/social-scheduler/service.py",
             "modules/social-scheduler/loop.py",
             "modules/triage-brain/main.py"]
    assert dep.map_files_to_services(files, MAP) == ["diracatron", "social_scheduler"]

def test_map_files_ignores_non_module_and_unknown():
    files = ["README.md", "eva-start.sh", "modules/unknown-mod/x.py", "docs/notes.md"]
    assert dep.map_files_to_services(files, MAP) == []

def test_map_files_dedupes_same_service():
    files = ["modules/channels/a.py", "modules/channels/b.py"]
    assert dep.map_files_to_services(files, MAP) == ["channels"]

def test_default_module_map_has_known_services():
    mm = dep.default_module_map()
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
# eva target (pull_and_restart) — offline, up-to-date, check failure
# ---------------------------------------------------------------------------

def test_offline_check_is_noop():
    svc = DeployerService(offline=True, state=StubStateLedgerClient())
    res = svc.check()
    assert res["action"] == "check" and res["ok"] is True
    assert all(t["action"] == "noop_offline" for t in res["targets"])
    assert svc.launcher is None and svc.gate is None and svc.vercel is None

def test_up_to_date_when_local_equals_remote():
    git = FakeGit(local="same", remote="same")
    svc = _svc(git)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "up_to_date" and res["ok"] is True
    assert git.pulled == 0

def test_check_failed_when_remote_sha_unresolved():
    git = FakeGit(local="aaa", remote="")
    state = StubStateLedgerClient()
    svc = _svc(git, state=state)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "check_failed" and res["ok"] is False
    assert git.pulled == 0
    assert any(e["event_type"] == "deploy_check_failed" for e in state.events)


# ---------------------------------------------------------------------------
# eva target — the happy self-deploy path
# ---------------------------------------------------------------------------

def test_deploy_applied_restarts_only_changed_services():
    git = FakeGit(local="old1234", remote="new5678",
                  pull={"ok": True, "conflict": False,
                        "old_sha": "old1234", "new_sha": "new5678"},
                  changed=["modules/social-scheduler/loop.py", "README.md"])
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert res["old_sha"] == "old1234" and res["new_sha"] == "new5678"
    assert res["services"] == ["social_scheduler"]
    assert launcher.restarted == ["social_scheduler"]  # README.md → no restart
    assert any(e["event_type"] == "deploy_applied" for e in state.events)

def test_deploy_with_no_service_changes_restarts_nothing():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"},
                  changed=["README.md", "SYSTEM_MAP.md"])
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert res["services"] == [] and launcher.restarted == []


# ---------------------------------------------------------------------------
# eva SAFETY — conflict / non-fast-forward NEVER restarts anything
# ---------------------------------------------------------------------------

def test_conflict_aborts_and_never_restarts():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": False, "conflict": True, "old_sha": "old",
                        "new_sha": "old", "error": "Not possible to fast-forward"})
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "deploy_skipped_conflict" and res["ok"] is False
    assert launcher.restarted == []
    assert any(e["event_type"] == "deploy_skipped_conflict" for e in state.events)

def test_pull_failure_emits_deploy_failed_without_restart():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": False, "conflict": False, "old_sha": "old",
                        "new_sha": "old", "error": "fetch failed: network"})
    launcher = FakeLauncher(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, launcher=launcher, state=state)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "deploy_failed" and res["ok"] is False
    assert launcher.restarted == []
    assert any(e["event_type"] == "deploy_failed" for e in state.events)


# ---------------------------------------------------------------------------
# eva SAFETY — gated on no in-flight work
# ---------------------------------------------------------------------------

def test_restart_waits_for_inflight_to_clear():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"},
                  changed=["modules/social-scheduler/loop.py"])
    gate = FakeGate(busy_ticks=2)
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher, gate=gate)
    res = svc.check_target(EVA_TARGET)
    assert res["action"] == "deploy_applied" and res["ok"] is True
    assert launcher.restarted == ["social_scheduler"]
    assert res["restarts"][0]["wait"]["attempts"] == 3

def test_restart_skipped_when_inflight_never_clears():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"},
                  changed=["modules/social-scheduler/loop.py"])
    gate = FakeGate(busy_ticks=999)
    launcher = FakeLauncher(ok=True)
    svc = _svc(git, launcher=launcher, gate=gate)
    res = svc.check_target(EVA_TARGET)
    assert launcher.restarted == []
    assert res["restarts"][0]["reason"] == "in_flight_timeout"
    assert res["action"] == "deploy_failed" and res["ok"] is False


# ---------------------------------------------------------------------------
# eva-landing target (vercel_prod)
# ---------------------------------------------------------------------------

def test_landing_up_to_date_skips_vercel():
    git = FakeGit(local="same", remote="same")
    vercel = FakeVercel(ok=True)
    svc = _svc(git, target=LANDING_TARGET, vercel=vercel)
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "up_to_date" and res["ok"] is True
    assert vercel.calls == []  # no new commit → vercel never runs
    assert git.pulled == 0

def test_landing_deploy_runs_vercel_prod():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"})
    vercel = FakeVercel(ok=True, url="https://eva-landing-xyz.vercel.app")
    state = StubStateLedgerClient()
    svc = _svc(git, target=LANDING_TARGET, vercel=vercel, state=state)
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "deploy_landing_applied" and res["ok"] is True
    assert res["old_sha"] == "old" and res["new_sha"] == "new"
    assert res["url"] == "https://eva-landing-xyz.vercel.app"
    assert len(vercel.calls) == 1 and vercel.calls[0]["path"] == "/tmp/eva-landing"
    assert git.pulled == 1  # pulled the new code before deploying
    assert any(e["event_type"] == "deploy_landing_applied" for e in state.events)

def test_landing_vercel_failure_reports_failed():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"})
    vercel = FakeVercel(ok=False)  # CLI fails
    state = StubStateLedgerClient()
    svc = _svc(git, target=LANDING_TARGET, vercel=vercel, state=state)
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "deploy_landing_failed" and res["ok"] is False
    assert len(vercel.calls) == 1  # attempted
    assert any(e["event_type"] == "deploy_landing_failed" for e in state.events)

def test_landing_conflict_never_runs_vercel():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": False, "conflict": True, "old_sha": "old",
                        "new_sha": "old", "error": "Not possible to fast-forward"})
    vercel = FakeVercel(ok=True)
    state = StubStateLedgerClient()
    svc = _svc(git, target=LANDING_TARGET, vercel=vercel, state=state)
    res = svc.check_target(LANDING_TARGET)
    # abort + log + skip — a broken/diverged tree is NEVER shipped
    assert res["action"] == "deploy_landing_failed" and res["ok"] is False
    assert res["vercel"] is False and vercel.calls == []
    assert any(e["event_type"] == "deploy_landing_failed" for e in state.events)

def test_landing_deploy_passes_token_to_vercel():
    old = dep.CHANNELS_CONFIG_PATH
    dep.CHANNELS_CONFIG_PATH = dep.Path("/nonexistent/eva/channels_config.json")
    os.environ["VERCEL_TOKEN"] = "TESTTOKEN"
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"})
    vercel = FakeVercel(ok=True)
    try:
        svc = _svc(git, target=LANDING_TARGET, vercel=vercel)
        svc.check_target(LANDING_TARGET)
        assert vercel.calls[0]["token"] == "TESTTOKEN"
    finally:
        dep.CHANNELS_CONFIG_PATH = old
        os.environ.pop("VERCEL_TOKEN", None)


# ---------------------------------------------------------------------------
# eva-landing SAFETY — one-tap approval gate before vercel --prod ships live
# ---------------------------------------------------------------------------

def _landing_svc(*, vercel=None, notifier=None, state=None, approval_timeout=5.0):
    """A remote-ahead landing service ready to hit the approval gate."""
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False,
                        "old_sha": "old", "new_sha": "new"},
                  changed=["index.html", "api/lead.js"])
    return git, _svc(git, target=LANDING_TARGET,
                     vercel=vercel or FakeVercel(ok=True),
                     notifier=notifier or StubApprovalNotifier(),
                     state=state or StubStateLedgerClient(),
                     approval_timeout=approval_timeout)


def test_landing_creates_pending_approval_and_holds_vercel():
    # remote is ahead → a pending_approval row is created and Slack is asked
    # BEFORE vercel is ever called; nothing ships until someone approves.
    notifier = StubApprovalNotifier()
    state = StubStateLedgerClient()
    vercel = FakeVercel(ok=True)
    _git, svc = _landing_svc(vercel=vercel, notifier=notifier, state=state)
    seen = []

    def hook(did):
        d = store.get_deploy(did, db_path=svc.db_path)
        seen.append(d["status"])
        svc.approve(did, False)  # end the wait (deny) so the test never spins

    svc._poll_hook = hook
    res = svc.check_target(LANDING_TARGET)
    # a pending_approval row existed mid-wait, Slack was asked, vercel held
    assert seen and seen[0] == store.STATUS_PENDING_APPROVAL
    assert len(notifier.requests) == 1
    assert vercel.calls == []  # vercel NOT called before approval
    assert any(e["event_type"] == "deploy_landing_pending" for e in state.events)
    # the Slack request carried the target repo, SHAs, and a changed-files summary
    req = notifier.requests[0]
    assert req["repo"] == "Mangotec333/eva-landing"
    assert req["old_sha"] == "old" and req["new_sha"] == "new"
    assert "index.html" in req["changed_summary"]


def test_landing_approved_runs_vercel_and_applies():
    notifier = StubApprovalNotifier()
    state = StubStateLedgerClient()
    vercel = FakeVercel(ok=True, url="https://eva-landing-xyz.vercel.app")
    _git, svc = _landing_svc(vercel=vercel, notifier=notifier, state=state)
    svc._poll_hook = lambda did: svc.approve(did, True, actor="founder")
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "deploy_landing_applied" and res["ok"] is True
    assert res["url"] == "https://eva-landing-xyz.vercel.app"
    assert len(vercel.calls) == 1  # ran only AFTER approval
    assert len(notifier.requests) == 1
    assert any(e["event_type"] == "deploy_landing_pending" for e in state.events)
    assert any(e["event_type"] == "deploy_landing_applied" for e in state.events)
    rows = store.list_deploys(db_path=svc.db_path)
    assert rows[0]["status"] == store.STATUS_APPLIED


def test_landing_denied_never_runs_vercel():
    notifier = StubApprovalNotifier()
    state = StubStateLedgerClient()
    vercel = FakeVercel(ok=True)
    _git, svc = _landing_svc(vercel=vercel, notifier=notifier, state=state)
    svc._poll_hook = lambda did: svc.approve(did, False)
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "deploy_landing_denied" and res["ok"] is False
    assert res["vercel"] is False and vercel.calls == []  # never shipped
    assert any(e["event_type"] == "deploy_landing_denied" for e in state.events)
    rows = store.list_deploys(db_path=svc.db_path)
    assert rows[0]["status"] == store.STATUS_DENIED


def test_landing_expires_when_unapproved():
    notifier = StubApprovalNotifier()
    state = StubStateLedgerClient()
    vercel = FakeVercel(ok=True)
    _git, svc = _landing_svc(vercel=vercel, notifier=notifier, state=state,
                             approval_timeout=0.0)
    svc._poll_hook = None  # nobody approves within the window
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "deploy_landing_expired" and res["ok"] is False
    assert res["vercel"] is False and vercel.calls == []  # never shipped
    assert any(e["event_type"] == "deploy_landing_expired" for e in state.events)
    rows = store.list_deploys(db_path=svc.db_path)
    assert rows[0]["status"] == store.STATUS_EXPIRED


def test_landing_offline_short_circuits_with_no_network():
    # EVA_DEPLOYER_OFFLINE=1 → the whole pass is a no-op: no git, no vercel, no
    # Slack. The gate never runs and the Stub notifier records nothing.
    svc = DeployerService(offline=True, targets=[LANDING_TARGET],
                          state=StubStateLedgerClient())
    assert isinstance(svc.notifier, StubApprovalNotifier)  # never the live Slack one
    res = svc.check_target(LANDING_TARGET)
    assert res["action"] == "noop_offline" and res["ok"] is True
    assert svc.vercel is None and svc.launcher is None and svc.gate is None
    assert svc.notifier.requests == []  # nothing was ever asked


def test_landing_approve_unknown_deploy():
    _git, svc = _landing_svc()
    assert svc.approve("no-such-id", True)["ok"] is False


def test_landing_approve_already_resolved_is_noop():
    _git, svc = _landing_svc()
    svc._poll_hook = lambda did: svc.approve(did, True)
    res = svc.check_target(LANDING_TARGET)
    again = svc.approve(res["deploy_id"], True)
    assert again["ok"] is False and again.get("noop") is True


def test_approval_timeout_env_override_and_default():
    os.environ.pop("EVA_DEPLOYER_APPROVAL_TIMEOUT", None)
    from service import _approval_timeout_default, DEFAULT_APPROVAL_TIMEOUT
    assert _approval_timeout_default() == float(DEFAULT_APPROVAL_TIMEOUT) == 600.0
    os.environ["EVA_DEPLOYER_APPROVAL_TIMEOUT"] = "42"
    try:
        assert _approval_timeout_default() == 42.0
    finally:
        os.environ.pop("EVA_DEPLOYER_APPROVAL_TIMEOUT", None)


# ---------------------------------------------------------------------------
# check() iterates ALL targets in one pass
# ---------------------------------------------------------------------------

def test_check_iterates_all_targets():
    eva_git = FakeGit(local="same", remote="same")  # eva up-to-date
    landing_git = FakeGit(local="old", remote="new",  # landing has a new commit
                          pull={"ok": True, "conflict": False,
                                "old_sha": "old", "new_sha": "new"})
    gits = {"eva": eva_git, "eva-landing": landing_git}
    vercel = FakeVercel(ok=True)
    svc = DeployerService(
        offline=False, targets=[EVA_TARGET, LANDING_TARGET],
        git_factory=lambda t: gits[t["name"]],
        launcher=FakeLauncher(), gate=FakeGate(), vercel=vercel,
        notifier=StubApprovalNotifier(),
        state=StubStateLedgerClient(), module_map=MAP,
        restart_backoff=0.0, approval_timeout=5.0, approval_poll_interval=0.0,
        db_path=_tmp_db(), sleep_fn=lambda s: None, now_fn=_clock())
    svc._poll_hook = lambda did: svc.approve(did, True)  # auto-approve landing
    res = svc.check()
    assert res["action"] == "check"
    by_name = {t["target"]: t for t in res["targets"]}
    assert by_name["eva"]["action"] == "up_to_date"
    assert by_name["eva-landing"]["action"] == "deploy_landing_applied"
    assert len(vercel.calls) == 1  # only the landing target deployed


# ---------------------------------------------------------------------------
# resilience — check_target() NEVER raises
# ---------------------------------------------------------------------------

def test_check_survives_git_exception():
    class BoomGit(FakeGit):
        def current_sha(self):
            raise RuntimeError("git blew up")

    state = StubStateLedgerClient()
    svc = _svc(BoomGit(), state=state)
    res = svc.check_target(EVA_TARGET)  # must NOT raise
    assert res["action"] == "error" and res["ok"] is False
    assert "RuntimeError" in res["error"]

def test_restart_failure_reports_deploy_failed():
    git = FakeGit(local="old", remote="new",
                  pull={"ok": True, "conflict": False, "old_sha": "old", "new_sha": "new"},
                  changed=["modules/channels/x.py"])
    launcher = FakeLauncher(ok=False)
    svc = _svc(git, launcher=launcher)
    res = svc.check_target(EVA_TARGET)
    assert launcher.restarted == ["channels"]
    assert res["action"] == "deploy_failed" and res["ok"] is False


# ---------------------------------------------------------------------------
# status / history
# ---------------------------------------------------------------------------

def test_status_reports_offline_targets_and_interval():
    svc = DeployerService(offline=True, state=StubStateLedgerClient())
    st = svc.status()
    assert st["offline"] is True
    assert st["poll_interval_seconds"] == 18000
    names = [t["name"] for t in st["targets"]]
    assert "eva" in names and "eva-landing" in names

def test_history_is_newest_first_and_bounded():
    git = FakeGit(local="same", remote="same")
    svc = _svc(git)
    for _ in range(3):
        svc.check()
    hist = svc.history(limit=2)
    assert hist["count"] == 3
    assert len(hist["items"]) == 2
    assert all(it["action"] == "check" for it in hist["items"])
    assert all(it["targets"][0]["action"] == "up_to_date" for it in hist["items"])


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
        return {"ok": True, "action": "check"}


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
    assert svc.checks == 1 and out["fired"] is True and out["action"] == "check"

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
    loop._run_forever()
    assert calls["n"] >= 3
    assert len(loop.fires) >= 2


# ---------------------------------------------------------------------------
# no hardcoded secrets anywhere in the module
# ---------------------------------------------------------------------------

def test_no_hardcoded_secrets():
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in ("deployer.py", "service.py", "loop.py", "main.py",
               "cli.py", "state_client.py", "approve.py", "store.py"):
        with open(os.path.join(here, fn), encoding="utf-8") as f:
            content = f.read()
        assert "ghp_" not in content, f"leaked GitHub token in {fn}"
        assert "github_pat_" not in content, f"leaked GitHub PAT in {fn}"
        # a real Vercel token is a 24-char hex; ensure none is baked in
        import re as _re
        assert not _re.search(r"\bvercel_[A-Za-z0-9]{20,}\b", content), \
            f"possible leaked Vercel token in {fn}"


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
