"""
EVA Diracatron — offline test suite (stub sources + stub dispatcher + stub
ledger, zero network). Nothing real (GHL / Slack / LinkedIn) is ever fired.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module
runs:

  python modules/triage-brain/test_diracatron.py
  (or)  cd modules/triage-brain && python test_diracatron.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EVA_DIRACATRON_OFFLINE"] = "1"

import diracatron
import store
from diracatron import StubDispatcher, StubSource
from service import DiracatronService
from state_client import StubStateLedgerClient


# ---------------------------------------------------------------------------
# Helpers (framework-free)
# ---------------------------------------------------------------------------

def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="diracatron_test_", suffix=".db")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    store.init_db(path)
    return path


def _candidates():
    return [
        {"kind": diracatron.KIND_NEW_LEAD, "entity_id": "lead-1",
         "summary": "New lead from landing page", "source": "eva-state",
         "payload": {"email": "a@b.co"}},
        {"kind": diracatron.KIND_BROKER_REPLY, "entity_id": "lead-2",
         "summary": "Broker replied", "source": "eva-state", "payload": {}},
        {"kind": diracatron.KIND_DEAL_SCORE, "entity_id": "deal-9",
         "summary": "Deal crossed threshold", "source": "eva-state",
         "payload": {"score": 92}},
        {"kind": diracatron.KIND_CONTENT_DRAFT, "entity_id": "draft-3",
         "summary": "Content draft pending approval", "source": "eva-state",
         "payload": {}},
        {"kind": diracatron.KIND_REVENUE_LEAK, "entity_id": "leak-4",
         "summary": "Revenue-leak play", "source": "eva-state", "payload": {}},
        {"kind": diracatron.KIND_STALLED_TASK, "entity_id": "task-5",
         "summary": "Stalled agent task", "source": "eva-state",
         "payload": {"agent": "ghl-agent"}},
    ]


def _svc(db, candidates=None, dispatcher=None, state=None):
    return DiracatronService(
        db_path=db,
        sources=[StubSource(candidates if candidates is not None else _candidates())],
        dispatcher=dispatcher or StubDispatcher(),
        state=state or StubStateLedgerClient(),
        offline=True,
    )


# ---------------------------------------------------------------------------
# Ranking / classification
# ---------------------------------------------------------------------------

def test_priority_order_broker_first():
    assert diracatron.PRIORITY[diracatron.KIND_BROKER_REPLY] > \
           diracatron.PRIORITY[diracatron.KIND_NEW_LEAD] > \
           diracatron.PRIORITY[diracatron.KIND_DEAL_SCORE] > \
           diracatron.PRIORITY[diracatron.KIND_STALLED_TASK]


def test_score_deal_threshold_bump():
    low = {"kind": diracatron.KIND_DEAL_SCORE, "payload": {"score": 10}}
    high = {"kind": diracatron.KIND_DEAL_SCORE, "payload": {"score": 95}}
    assert diracatron.score(high) > diracatron.score(low)


def test_score_urgent_bump():
    plain = {"kind": diracatron.KIND_NEW_LEAD, "payload": {}}
    urgent = {"kind": diracatron.KIND_NEW_LEAD, "payload": {"urgent": True}}
    assert diracatron.score(urgent) == diracatron.score(plain) + 20


def test_normalise_event_maps_and_ignores():
    mapped = diracatron.normalise_event(
        {"event_type": "lead_captured", "entity_id": "x", "summary": "s"})
    assert mapped and mapped["kind"] == diracatron.KIND_NEW_LEAD
    assert diracatron.normalise_event({"event_type": "some_noise"}) is None


def test_route_for_stalled_uses_payload_agent():
    cand = {"kind": diracatron.KIND_STALLED_TASK, "payload": {"agent": "deal-scout"}}
    assert diracatron.route_for(cand) == "deal-scout"
    cand2 = {"kind": diracatron.KIND_NEW_LEAD, "payload": {}}
    assert diracatron.route_for(cand2) == "ghl-agent"


# ---------------------------------------------------------------------------
# run_pass — poll, rank, idempotent queue
# ---------------------------------------------------------------------------

def test_run_pass_ranks_queue():
    result = _svc(_new_db()).run_pass()
    assert result["candidates"] == 6
    assert result["open"] == 6
    kinds = [i["kind"] for i in result["queue"]]
    assert kinds[0] == diracatron.KIND_BROKER_REPLY


def test_run_pass_is_idempotent():
    db = _new_db()
    svc = _svc(db)
    svc.run_pass()
    second = svc.run_pass()
    assert second["open"] == 6
    assert len(store.list_queue(status=store.STATUS_OPEN, path=db)) == 6


def test_run_pass_emits_to_ledger():
    db = _new_db()
    state = StubStateLedgerClient()
    _svc(db, state=state).run_pass()
    assert any(e["event_type"] == "triage_pass" for e in state.events)


# ---------------------------------------------------------------------------
# dispatch — route, mark, log, learn
# ---------------------------------------------------------------------------

def test_dispatch_routes_and_records():
    db = _new_db()
    dispatcher = StubDispatcher()
    state = StubStateLedgerClient()
    svc = _svc(db, dispatcher=dispatcher, state=state)
    svc.run_pass()
    top = store.list_queue(status=store.STATUS_OPEN, path=db)[0]

    res = svc.dispatch(top["id"])
    assert res["ok"] is True
    assert res["agent"] == "pathfinder"  # broker_reply → pathfinder
    assert dispatcher.calls and dispatcher.calls[0]["agent"] == "pathfinder"
    assert store.get_item(top["id"], path=db)["status"] == store.STATUS_DISPATCHED
    assert any(e["event_type"] == "triage_dispatch" for e in state.events)
    assert store.list_dispatches(path=db)


def test_dispatch_unknown_item():
    res = _svc(_new_db()).dispatch("does-not-exist")
    assert res["ok"] is False
    assert "not found" in res["error"]


def test_dispatch_twice_is_guarded():
    db = _new_db()
    svc = _svc(db)
    svc.run_pass()
    top = store.list_queue(status=store.STATUS_OPEN, path=db)[0]
    svc.dispatch(top["id"])
    again = svc.dispatch(top["id"])
    assert again["ok"] is False
    assert "dispatched" in again["error"]


def test_stalled_task_routes_to_payload_agent():
    db = _new_db()
    svc = _svc(db)
    svc.run_pass()
    stalled = next(i for i in store.list_queue(status=store.STATUS_OPEN, path=db)
                   if i["kind"] == diracatron.KIND_STALLED_TASK)
    assert stalled["target_agent"] == "ghl-agent"


# ---------------------------------------------------------------------------
# Slack alert is best-effort (no token -> honest ok=False, no network)
# ---------------------------------------------------------------------------

def test_slack_alert_no_token():
    os.environ.pop("SLACK_BOT_TOKEN", None)
    res = diracatron.slack_alert("hello")
    assert res["ok"] is False


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
