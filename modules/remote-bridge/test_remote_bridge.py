"""
EVA Remote-Bridge — offline test suite (zero network, zero real dispatch).

Nothing real is EVER contacted: Diracatron and the Eva State Ledger are replaced
with in-memory stubs, and every run uses a throwaway temp sqlite. The HTTP
surface is exercised with FastAPI's TestClient (which runs BackgroundTasks
synchronously after the response, so a submitted instruction has already been
dispatched by the time we read its status back).

Runs under real pytest, or standalone via the bundled shim when pytest is not
installed (a networkless sandbox):

  python test_remote_bridge.py
  (or)  python -m pytest modules/remote-bridge/test_remote_bridge.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import-time posture: offline so the module-level service never touches network.
os.environ["EVA_REMOTE_BRIDGE_OFFLINE"] = "1"

try:
    import pytest
except ImportError:  # networkless sandbox — use the bundled shim
    import _pytest_shim as pytest  # type: ignore

from fastapi.testclient import TestClient

import database as db
import main
from dispatch_client import StubDispatchClient
from service import RemoteBridgeService
from state_client import StubStateLedgerClient

TOKEN = "test-secret-key"


class RaisingStateClient(StubStateLedgerClient):
    """A state client whose emit always blows up — proves an audit failure
    never blocks or fails the HTTP response."""

    def emit(self, **kwargs):
        raise RuntimeError("eva-state is down")


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="remote_bridge_", suffix=".db")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return path


def _install_service(*, dispatcher=None, state=None) -> RemoteBridgeService:
    """Build a fully-stubbed service, wire it into the app, reset rate limits."""
    svc = RemoteBridgeService(
        db_path=_tmp_db(), offline=True,
        dispatcher=dispatcher or StubDispatchClient(),
        state=state or StubStateLedgerClient())
    main.service = svc
    with main._rate_lock:
        main._rate_state.clear()
    return svc


def _client(*, api_key=TOKEN, dispatcher=None, state=None):
    if api_key is None:
        os.environ.pop(main.API_KEY_ENV, None)
    else:
        os.environ[main.API_KEY_ENV] = api_key
    svc = _install_service(dispatcher=dispatcher, state=state)
    return TestClient(main.app), svc


def _auth(token=TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fail-closed: no API key configured
# ---------------------------------------------------------------------------

def test_missing_api_key_fails_closed_on_all_remote_routes():
    client, _ = _client(api_key=None)
    # Every /remote/* route returns 503, with or without a token.
    assert client.post("/remote/instruct", json={"goal": "x"}).status_code == 503
    assert client.get("/remote/instruct").status_code == 503
    assert client.get("/remote/instruct/abc").status_code == 503
    assert client.get("/remote/instruct/abc/ledger").status_code == 503
    # even presenting a bearer token cannot open the door when unconfigured
    assert client.get("/remote/instruct", headers=_auth()).status_code == 503


def test_health_needs_no_auth_and_never_leaks_key():
    client, _ = _client(api_key=TOKEN)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["api_key_configured"] is True
    # the boolean only — the key value must never appear anywhere in the payload
    assert TOKEN not in r.text


def test_health_reports_unconfigured_when_no_key():
    client, _ = _client(api_key=None)
    body = client.get("/health").json()
    assert body["api_key_configured"] is False


# ---------------------------------------------------------------------------
# Auth: wrong token → 401, correct token → immediate ack
# ---------------------------------------------------------------------------

def test_wrong_token_rejected():
    client, svc = _client()
    r = client.post("/remote/instruct", json={"goal": "do a thing"},
                    headers=_auth("nope"))
    assert r.status_code == 401
    # missing header too
    assert client.post("/remote/instruct", json={"goal": "x"}).status_code == 401
    # the rejection was audited
    assert any(e["event_type"] == "remote_instruction_unauthorized"
               for e in svc.state.events)


def test_correct_token_returns_immediate_ack():
    client, _ = _client()
    r = client.post("/remote/instruct", json={"goal": "review the pipeline"},
                    headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == db.STATUS_RECEIVED
    assert body["instruction_id"]


# ---------------------------------------------------------------------------
# Background dispatch: complete + failed paths
# ---------------------------------------------------------------------------

def test_background_dispatch_marks_complete():
    dispatcher = StubDispatchClient(result={"ok": True, "planner": "stub",
                                            "steps": [], "results": []})
    client, svc = _client(dispatcher=dispatcher)
    iid = client.post("/remote/instruct", json={"goal": "ship it"},
                      headers=_auth()).json()["instruction_id"]
    # TestClient already ran the background task → status is terminal.
    record = client.get(f"/remote/instruct/{iid}", headers=_auth()).json()
    assert record["status"] == db.STATUS_COMPLETE
    assert record["dispatch_result"]["ok"] is True
    assert len(dispatcher.calls) == 1
    types = [e["event_type"] for e in svc.state.events]
    assert "remote_instruction_received" in types
    assert "remote_instruction_dispatched" in types
    assert "remote_instruction_complete" in types


def test_dispatch_raises_is_captured_as_failed_not_crashed():
    dispatcher = StubDispatchClient(raise_exc=RuntimeError("diracatron exploded"))
    client, svc = _client(dispatcher=dispatcher)
    r = client.post("/remote/instruct", json={"goal": "boom"}, headers=_auth())
    assert r.status_code == 200  # the ack still succeeded — never crashed
    iid = r.json()["instruction_id"]
    record = client.get(f"/remote/instruct/{iid}", headers=_auth()).json()
    assert record["status"] == db.STATUS_FAILED
    assert "diracatron exploded" in record["error"]
    assert any(e["event_type"] == "remote_instruction_failed"
               for e in svc.state.events)


def test_dispatch_reporting_not_ok_is_failed():
    dispatcher = StubDispatchClient(result={"ok": False, "error": "no agent"})
    client, _ = _client(dispatcher=dispatcher)
    iid = client.post("/remote/instruct", json={"goal": "x"},
                      headers=_auth()).json()["instruction_id"]
    record = client.get(f"/remote/instruct/{iid}", headers=_auth()).json()
    assert record["status"] == db.STATUS_FAILED
    assert "no agent" in record["error"]


# ---------------------------------------------------------------------------
# Reads: status 404, list newest-first + limit
# ---------------------------------------------------------------------------

def test_status_unknown_id_404():
    client, _ = _client()
    assert client.get("/remote/instruct/does-not-exist",
                      headers=_auth()).status_code == 404


def test_list_newest_first_and_respects_limit():
    client, _ = _client()
    goals = ["first", "second", "third"]
    for g in goals:
        client.post("/remote/instruct", json={"goal": g}, headers=_auth())
    body = client.get("/remote/instruct?limit=2", headers=_auth()).json()
    assert body["count"] == 2
    # newest first → "third" then "second"
    assert body["items"][0]["goal"] == "third"
    assert body["items"][1]["goal"] == "second"


def test_empty_goal_rejected():
    client, _ = _client()
    assert client.post("/remote/instruct", json={"goal": "   "},
                       headers=_auth()).status_code == 400


# ---------------------------------------------------------------------------
# Ledger: populated + append-only (direct UPDATE / DELETE rejected)
# ---------------------------------------------------------------------------

def test_ledger_records_lifecycle():
    client, _ = _client()
    iid = client.post("/remote/instruct", json={"goal": "trace me"},
                      headers=_auth()).json()["instruction_id"]
    body = client.get(f"/remote/instruct/{iid}/ledger", headers=_auth()).json()
    events = [e["event_type"] for e in body["ledger"]]
    assert "remote_instruction_received" in events
    assert "remote_instruction_dispatched" in events
    assert "remote_instruction_complete" in events


def test_ledger_is_append_only():
    _, svc = _client()
    svc.store.append_ledger(event_type="remote_instruction_received",
                            entity_id="e1", actor="founder")
    conn = svc.store._connect()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE instruction_ledger SET actor = 'x'")
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM instruction_ledger")
        conn.commit()


# ---------------------------------------------------------------------------
# Rate limiting: 429 after threshold
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429_after_threshold():
    client, svc = _client()
    ok = 0
    limited = 0
    for _ in range(main.RATE_LIMIT_MAX + 5):
        r = client.get("/remote/instruct", headers=_auth())
        if r.status_code == 200:
            ok += 1
        elif r.status_code == 429:
            limited += 1
    assert ok == main.RATE_LIMIT_MAX
    assert limited == 5
    assert any(e["event_type"] == "remote_instruction_rate_limited"
               for e in svc.state.events)


# ---------------------------------------------------------------------------
# Resilience: eva-state emission failure must NOT block the response
# ---------------------------------------------------------------------------

def test_state_emit_failure_does_not_block_response():
    client, _ = _client(state=RaisingStateClient())
    r = client.post("/remote/instruct", json={"goal": "still works"},
                    headers=_auth())
    assert r.status_code == 200  # audit blew up internally, response is fine
    iid = r.json()["instruction_id"]
    # dispatch still completed despite every emit raising
    record = client.get(f"/remote/instruct/{iid}", headers=_auth()).json()
    assert record["status"] == db.STATUS_COMPLETE


# ---------------------------------------------------------------------------
# No hardcoded secrets in the module
# ---------------------------------------------------------------------------

def test_no_hardcoded_secrets():
    import re as _re
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in ("main.py", "service.py", "database.py", "dispatch_client.py",
               "state_client.py", "cli.py"):
        with open(os.path.join(here, fn), encoding="utf-8") as f:
            content = f.read()
        assert not _re.search(r"xoxb-\d{6,}-", content), f"leaked slack token in {fn}"
        assert not _re.search(r"\bAKIA[0-9A-Z]{16}\b", content), f"leaked AWS key in {fn}"


if __name__ == "__main__":
    raise SystemExit(pytest._run(dict(globals())))
