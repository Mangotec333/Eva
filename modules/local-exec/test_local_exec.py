"""
EVA Local-Exec — offline test suite (mock subprocess, zero real commands).

Nothing real is EVER executed: ``exec.subprocess`` is replaced with a fake that
records calls and returns canned results (and can be told to raise), the Slack
notifier + state ledger are stubs, and every run is written to a throwaway temp
sqlite. A real command can never run from these tests.

Stdlib-only runner (no pytest dependency):

  python modules/local-exec/test_local_exec.py
  (or)  cd modules/local-exec && python test_local_exec.py
"""

from __future__ import annotations

import os
import subprocess as _real_sub
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import exec as ex
import store
from approve import StubApprovalNotifier
from state_client import StubStateLedgerClient


# ---------------------------------------------------------------------------
# Fake subprocess — installed globally so no real command can ever run
# ---------------------------------------------------------------------------

class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeSubprocess:
    TimeoutExpired = _real_sub.TimeoutExpired

    def __init__(self):
        self.calls = []
        self.result = FakeCompleted(0, "", "")
        self.exc = None

    def run(self, argv, **kwargs):
        self.calls.append({"argv": argv, "kwargs": kwargs})
        if self.exc is not None:
            raise self.exc
        return self.result

    def reset(self, result=None, exc=None):
        self.calls = []
        self.result = result or FakeCompleted(0, "", "")
        self.exc = exc


FAKE = FakeSubprocess()
ex.subprocess = FAKE  # global guard: exec never touches the real subprocess


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="local_exec_", suffix=".db")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return path


def _no_offline():
    os.environ.pop("EVA_LOCAL_EXEC_OFFLINE", None)


def _svc(**kw):
    from service import LocalExecService
    _no_offline()
    defaults = dict(
        offline=False, state=StubStateLedgerClient(),
        notifier=StubApprovalNotifier(), allowlist=ex.load_allowlist(),
        db_path=_tmp_db(), sleep_fn=lambda s: None, now_fn=_clock(),
        poll_interval=0.0)
    defaults.update(kw)
    return LocalExecService(**defaults)


def _clock():
    """A monotonically advancing fake clock (so timeouts are deterministic)."""
    state = {"t": 0.0}

    def now():
        state["t"] += 0.001
        return state["t"]
    return now


# ---------------------------------------------------------------------------
# Allowlist matching (pure)
# ---------------------------------------------------------------------------

AL = ex.load_allowlist()


def test_allow_git_read_ops():
    for sub in ("status", "pull", "diff", "log"):
        r = ex.match_allowlist(["git", sub], None, AL)
        assert r is not None and r["name"].startswith("git-"), sub


def test_allow_curl_localhost():
    assert ex.match_allowlist(["curl", "localhost:8765/health"], None, AL)
    assert ex.match_allowlist(["curl", "http://127.0.0.1:8770/x"], None, AL)


def test_curl_remote_is_not_allowlisted():
    assert ex.match_allowlist(["curl", "https://evil.example.com/steal"], None, AL) is None


def test_curl_with_method_flag_matches_launcher_restart():
    r = ex.match_allowlist(
        ["curl", "-X", "POST", "localhost:8768/restart/voice"], None, AL)
    assert r is not None and r["name"] == "service-restart"


def test_service_restart_via_launcher():
    r = ex.match_allowlist(["curl", "localhost:8768/stop/deployer"], None, AL)
    assert r is not None and r["name"] == "service-restart"


def test_vercel_prod_requires_git_repo():
    d = tempfile.mkdtemp(prefix="vc_")
    # no .git → not allowlisted
    assert ex.match_allowlist(["vercel", "--prod"], d, AL) is None
    os.mkdir(os.path.join(d, ".git"))
    r = ex.match_allowlist(["vercel", "--prod"], d, AL)
    assert r is not None and r["name"] == "vercel-prod"


def test_env_swap_sed_on_eva_json_allowed():
    p = os.path.join(str(os.path.expanduser("~")), ".eva", "channels_config.json")
    r = ex.match_allowlist(["sed", "-i", "s/OLD/TOKEN=newval/", p], None, AL)
    assert r is not None and r["name"] == "env-swap-sed"


def test_env_swap_rejects_disallowed_path():
    assert ex.match_allowlist(["sed", "-i", "s/a/KEY=v/", "/etc/passwd"], None, AL) is None


def test_env_swap_rejects_extra_path():
    p = os.path.join(str(os.path.expanduser("~")), ".eva", "x.json")
    # a second, non-allowed path present → refuse
    assert ex.match_allowlist(
        ["sed", "-i", "s/a/KEY=v/", p, "/tmp/other.json"], None, AL) is None


def test_dangerous_command_not_allowlisted():
    assert ex.match_allowlist(["rm", "-rf", "/"], None, AL) is None
    assert ex.match_allowlist(["python", "-c", "print(1)"], None, AL) is None
    assert ex.match_allowlist(["git", "push", "--force"], None, AL) is None


def test_config_file_allowlist_is_primary():
    fd, cfg = tempfile.mkstemp(prefix="al_", suffix=".json")
    os.close(fd)
    import json
    with open(cfg, "w") as f:
        json.dump({"allowlist": [{"name": "echo-only", "prefix": ["echo"]}]}, f)
    try:
        al = ex.load_allowlist(cfg)
        assert [r["name"] for r in al] == ["echo-only"]
        assert ex.match_allowlist(["echo", "hi"], None, al) is not None
        assert ex.match_allowlist(["git", "status"], None, al) is None
    finally:
        os.unlink(cfg)


def test_config_allowlist_cannot_inject_unknown_check():
    fd, cfg = tempfile.mkstemp(prefix="al_", suffix=".json")
    os.close(fd)
    import json
    with open(cfg, "w") as f:
        json.dump({"allowlist": [{"name": "x", "prefix": ["rm"], "check": "pwn"}]}, f)
    try:
        al = ex.load_allowlist(cfg)
        # unknown check is dropped → rule becomes a bare prefix allow (still only
        # what the operator explicitly wrote into their own local file)
        assert al[0].get("check") is None
    finally:
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------

def test_mask_bearer_token():
    out, did = ex.mask_secrets("Authorization: Bearer abc123DEF456ghi789tokens")
    assert did and "abc123DEF456" not in out and ex.MASK_TOKEN in out


def test_mask_aws_key():
    out, did = ex.mask_secrets("aws key AKIAIOSFODNN7EXAMPLE here")
    assert did and "AKIAIOSFODNN7EXAMPLE" not in out


def test_mask_slack_and_github_tokens():
    # Tokens are assembled at runtime so no literal secret shape lives in source
    # (keeps GitHub push-protection / secret-scanning happy — these are fakes).
    slack = "xox" + "b-1234567890-abcdefghijklmno"
    github = "ghp_" + "a1" * 12
    out, did = ex.mask_secrets(slack + " and " + github)
    assert did and "1234567890-abcdefghijklmno" not in out and "ghp_a1a1" not in out


def test_mask_assignment():
    out, did = ex.mask_secrets("password=SuperSecret123 API_KEY=longvalue1234567")
    assert did and "SuperSecret123" not in out and "longvalue1234567" not in out


def test_mask_generic_high_entropy():
    out, did = ex.mask_secrets("token blob aB3xY9Qw12Zk88Lm44Np00 end")
    assert did and "aB3xY9Qw12Zk88Lm44Np00" not in out


def test_benign_text_not_masked():
    out, did = ex.mask_secrets("hello world nothing to hide here")
    assert not did and out == "hello world nothing to hide here"


def test_mask_argv_flags_secret():
    argv, did = ex.mask_argv(["curl", "-H", "Authorization: Bearer sk-abcd1234efgh5678ijkl"])
    assert did and all("sk-abcd1234" not in a for a in argv)


# ---------------------------------------------------------------------------
# Runner — offline no-op + mocked live runs (never real)
# ---------------------------------------------------------------------------

def test_offline_run_never_spawns_subprocess():
    FAKE.reset()
    os.environ["EVA_LOCAL_EXEC_OFFLINE"] = "1"
    try:
        res = ex.run_command("git", ["status"])
        assert res["ok"] and res.get("offline") is True
        assert FAKE.calls == []  # nothing real ran
    finally:
        _no_offline()


def test_run_command_masks_stdout():
    FAKE.reset(FakeCompleted(0, "token=abcd1234EFGH5678 wxyz\n", ""))
    _no_offline()
    res = ex.run_command("git", ["status"])
    assert res["ok"] and res["masked"] and "abcd1234EFGH5678" not in res["stdout"]
    assert FAKE.calls[0]["kwargs"]["shell"] is False  # never a shell string


def test_run_command_timeout_is_caught():
    FAKE.reset(exc=_real_sub.TimeoutExpired(cmd="git", timeout=1))
    _no_offline()
    res = ex.run_command("git", ["status"], timeout=1)
    assert not res["ok"] and "timed out" in res["stderr"]


def test_run_command_missing_binary_is_caught():
    FAKE.reset(exc=FileNotFoundError())
    _no_offline()
    res = ex.run_command("nope", [])
    assert not res["ok"] and "not found" in res["stderr"]


def test_run_command_never_raises():
    FAKE.reset(exc=RuntimeError("boom"))
    _no_offline()
    res = ex.run_command("git", ["status"])  # must NOT raise
    assert not res["ok"] and "RuntimeError" in res["stderr"]


# ---------------------------------------------------------------------------
# Service — allowlisted auto-run + audit
# ---------------------------------------------------------------------------

def test_allowlisted_runs_and_audits():
    FAKE.reset(FakeCompleted(0, "clean\n", ""))
    state = StubStateLedgerClient()
    svc = _svc(state=state)
    res = svc.exec_command("git", ["status"])
    assert res["ok"] and res["status"] == store.STATUS_ALLOWLISTED
    assert res["rule"] == "git-status" and len(FAKE.calls) == 1
    assert any(e["event_type"] == "local_exec_run" for e in state.events)
    hist = svc.history()
    assert hist["count"] == 1 and hist["items"][0]["status"] == store.STATUS_ALLOWLISTED


def test_failed_command_audited_as_failed():
    FAKE.reset(FakeCompleted(1, "", "fatal: not a repo\n"))
    state = StubStateLedgerClient()
    svc = _svc(state=state)
    res = svc.exec_command("git", ["status"])
    assert not res["ok"] and res["status"] == store.STATUS_FAILED
    assert any(e["event_type"] == "local_exec_failed" for e in state.events)


# ---------------------------------------------------------------------------
# Service — non-allowlisted gate: pending → approve → runs
# ---------------------------------------------------------------------------

def test_non_allowlist_blocks_then_approved_runs():
    FAKE.reset(FakeCompleted(0, "done\n", ""))
    state = StubStateLedgerClient()
    notifier = StubApprovalNotifier()
    svc = _svc(state=state, notifier=notifier)
    # approve on the first poll iteration (simulates POST /approve arriving)
    svc._poll_hook = lambda rid: svc.approve(rid, True, actor="founder")
    res = svc.exec_command("rm", ["/tmp/whatever"], approval_timeout=5.0)
    assert res["status"] == store.STATUS_APPROVED and res["ok"]
    assert len(notifier.requests) == 1  # Slack approval was requested
    assert len(FAKE.calls) == 1  # ran only AFTER approval
    types = [e["event_type"] for e in state.events]
    assert "local_exec_blocked" in types and "local_exec_approved" in types


def test_non_allowlist_denied_never_runs():
    FAKE.reset(FakeCompleted(0, "should-not-run\n", ""))
    state = StubStateLedgerClient()
    svc = _svc(state=state)
    svc._poll_hook = lambda rid: svc.approve(rid, False)
    res = svc.exec_command("rm", ["-rf", "/tmp/x"], approval_timeout=5.0)
    assert res["status"] == store.STATUS_DENIED and not res["ok"]
    assert FAKE.calls == []  # never executed
    assert any(e["event_type"] == "local_exec_denied" for e in state.events)


def test_non_allowlist_expires_when_unapproved():
    FAKE.reset(FakeCompleted(0, "nope\n", ""))
    state = StubStateLedgerClient()
    svc = _svc(state=state)  # no poll_hook → nobody approves
    res = svc.exec_command("shutdown", ["-h", "now"], approval_timeout=0.0)
    assert res["status"] == store.STATUS_EXPIRED and not res["ok"]
    assert FAKE.calls == []
    assert any(e["event_type"] == "local_exec_expired" for e in state.events)


def test_no_raw_secret_persisted_for_pending():
    FAKE.reset()
    svc = _svc()  # nobody approves; pending row persists
    svc.exec_command("deploy", ["--token", "sk-abcd1234EFGH5678ijkl9012"],
                     approval_timeout=0.0)
    rows = store.list_runs(path=svc.db_path)
    assert rows and all("sk-abcd1234EFGH5678" not in str(r["args"]) for r in rows)
    assert rows[0]["masked"] is True


# ---------------------------------------------------------------------------
# Service — approve edge cases, status, history, resilience
# ---------------------------------------------------------------------------

def test_approve_unknown_run():
    svc = _svc()
    assert svc.approve("no-such-id", True)["ok"] is False


def test_approve_already_resolved_is_noop():
    FAKE.reset(FakeCompleted(0, "ok\n", ""))
    svc = _svc()
    svc._poll_hook = lambda rid: svc.approve(rid, True)
    res = svc.exec_command("rm", ["x"], approval_timeout=5.0)
    again = svc.approve(res["run_id"], True)
    assert again["ok"] is False and again.get("noop") is True


def test_status_reports_allowlist_and_counts():
    FAKE.reset(FakeCompleted(0, "ok\n", ""))
    svc = _svc()
    svc.exec_command("git", ["status"])
    st = svc.status()
    assert st["offline"] is False
    assert "git-status" in st["allowlist"] and st["allowlist_count"] > 0
    assert st["runs_by_status"].get(store.STATUS_ALLOWLISTED) == 1
    assert "loopback" in st["bind"]


def test_history_is_newest_first():
    FAKE.reset(FakeCompleted(0, "ok\n", ""))
    svc = _svc()
    svc.exec_command("git", ["status"])
    svc.exec_command("git", ["log"])
    hist = svc.history(limit=10)
    assert hist["count"] == 2
    assert hist["items"][0]["command"] == "git" and hist["items"][0]["args"] == ["log"]


def test_exec_never_crashes_on_internal_error():
    svc = _svc()
    # force an internal failure by breaking the allowlist matcher
    svc.allowlist = None

    def boom(*a, **k):
        raise RuntimeError("kaboom")
    orig = ex.match_allowlist
    ex.match_allowlist = boom
    try:
        res = svc.exec_command("git", ["status"])  # must NOT raise
        assert not res["ok"] and "kaboom" in res.get("error", "")
    finally:
        ex.match_allowlist = orig


# ---------------------------------------------------------------------------
# Localhost-bind assertion (the hard safety guarantee)
# ---------------------------------------------------------------------------

def test_bind_refuses_non_loopback():
    os.environ["EVA_LOCAL_EXEC_OFFLINE"] = "1"
    try:
        import main
        for bad in ("0.0.0.0", "192.168.1.10", "::", "10.0.0.5"):
            raised = False
            try:
                main.assert_localhost_bind(bad)
            except SystemExit:
                raised = True
            assert raised, f"should refuse {bad}"
    finally:
        _no_offline()


def test_bind_allows_loopback():
    os.environ["EVA_LOCAL_EXEC_OFFLINE"] = "1"
    try:
        import main
        for good in ("127.0.0.1", "localhost", "::1"):
            main.assert_localhost_bind(good)  # must NOT raise
    finally:
        _no_offline()


# ---------------------------------------------------------------------------
# No hardcoded secrets in the module
# ---------------------------------------------------------------------------

def test_no_hardcoded_secrets():
    import re as _re
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in ("exec.py", "approve.py", "service.py", "state_client.py",
               "store.py", "main.py", "cli.py"):
        with open(os.path.join(here, fn), encoding="utf-8") as f:
            content = f.read()
        assert "ghp_" + "" not in content or "ghp_[" in content or "ghp_" in content and "re.compile" in content
        # ensure no literal Slack bot token / AWS key baked in
        assert not _re.search(r"xoxb-\d{6,}-", content), f"leaked slack token in {fn}"
        assert not _re.search(r"\bAKIA[0-9A-Z]{16}\b", content), f"leaked AWS key in {fn}"


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
            import traceback
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
        else:
            passed += 1
            print(f"PASS {t.__name__}")
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
