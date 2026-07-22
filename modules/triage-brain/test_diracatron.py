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
from deal_source import DealScoutSource, MarketSignalSource
from diracatron import StubDispatcher, StubSource
from dispatch_brain import HeuristicPlanner, LLMPlanner, build_planner
from registry import AgentRegistry, StubInvoker, build_registry
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


def _svc(db, candidates=None, dispatcher=None, state=None, planner=None,
         invoker=None):
    return DiracatronService(
        db_path=db,
        sources=[StubSource(candidates if candidates is not None else _candidates())],
        dispatcher=dispatcher or StubDispatcher(),
        state=state or StubStateLedgerClient(),
        planner=planner,
        invoker=invoker or StubInvoker(),
        offline=True,
    )


class _ScriptedClient:
    """A stub BrainClient returning a fixed JSON plan (no network)."""

    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, *, system, messages, max_tokens=0, model=""):  # noqa: D401
        return {"content": self._content, "error": None,
                "usage": {"input_tokens": 1, "output_tokens": 1}}


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


def test_normalise_event_maps_thesis_refuted():
    mapped = diracatron.normalise_event(
        {"event_type": "thesis_refuted", "entity_id": "run-1", "summary": "s"})
    assert mapped and mapped["kind"] == diracatron.KIND_THESIS_REFUTED


def test_normalise_event_maps_revenue_traction():
    mapped = diracatron.normalise_event(
        {"event_type": "revenue_traction_detected", "entity_id": "d-1", "summary": "s"})
    assert mapped and mapped["kind"] == diracatron.KIND_REVENUE_TRACTION


def test_normalise_event_maps_activity_digest():
    mapped = diracatron.normalise_event(
        {"event_type": "activity_digest_ready", "entity_id": "d-1", "summary": "s"})
    assert mapped and mapped["kind"] == diracatron.KIND_ACTIVITY_DIGEST


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
# First-principles rationale is stamped onto every ranked item
# ---------------------------------------------------------------------------

def test_first_principles_rationale_per_kind():
    for kind in (diracatron.KIND_BROKER_REPLY, diracatron.KIND_NEW_LEAD,
                 diracatron.KIND_DEAL_SCORE, diracatron.KIND_REVENUE_LEAK,
                 diracatron.KIND_CONTENT_DRAFT, diracatron.KIND_STALLED_TASK,
                 diracatron.KIND_ALIGNMENT_FLAG, diracatron.KIND_IDEA_SCORED,
                 diracatron.KIND_THESIS_REFUTED, diracatron.KIND_REVENUE_TRACTION,
                 diracatron.KIND_ACTIVITY_DIGEST):
        r = diracatron.first_principles_rationale({"kind": kind, "payload": {}})
        assert isinstance(r, str) and len(r) > 10


def test_thesis_refuted_routes_to_idea_generator_review():
    assert diracatron.ROUTES[diracatron.KIND_THESIS_REFUTED] == \
        ("idea-generator-agent", 8793, "/idea/review")
    assert diracatron.PRIORITY[diracatron.KIND_THESIS_REFUTED] >= \
        diracatron.PRIORITY[diracatron.KIND_DEAL_SCORE]


def test_revenue_traction_routes_and_outranks_deal_score():
    assert diracatron.ROUTES[diracatron.KIND_REVENUE_TRACTION] == \
        ("idea-generator-agent", 8793, "/idea/review")
    assert diracatron.PRIORITY[diracatron.KIND_REVENUE_TRACTION] > \
        diracatron.PRIORITY[diracatron.KIND_DEAL_SCORE]
    assert diracatron.PRIORITY[diracatron.KIND_REVENUE_TRACTION] < \
        diracatron.PRIORITY[diracatron.KIND_THESIS_REFUTED]


def test_activity_digest_is_informational_priority():
    assert diracatron.ROUTES[diracatron.KIND_ACTIVITY_DIGEST] == \
        ("idea-generator-agent", 8793, "/idea/review")
    assert diracatron.PRIORITY[diracatron.KIND_ACTIVITY_DIGEST] < \
        diracatron.PRIORITY[diracatron.KIND_STALLED_TASK]


def test_run_pass_stamps_rationale():
    db = _new_db()
    _svc(db).run_pass()
    for it in store.list_queue(status=store.STATUS_OPEN, path=db):
        assert it["payload"].get("rationale")


# ---------------------------------------------------------------------------
# Agent registry — data-driven, adding a lobe is a config edit
# ---------------------------------------------------------------------------

def test_registry_loads_all_lobes():
    reg = build_registry()
    slugs = reg.slugs()
    for expected in ("context-api", "deal-scout", "content-engine", "launcher",
                     "eva-state", "channels", "knowledge", "voice", "ghl-agent",
                     "treasurer", "social-scheduler", "deployer", "local-exec",
                     "ip-scout", "brand-builder", "idea-generator-agent",
                     "trend-agent", "activity-tracker-agent"):
        assert expected in slugs, expected
    assert len(slugs) == 18


def test_registry_port_and_base_url():
    reg = build_registry()
    assert reg.get("deal-scout").port == 8766
    # Port-less agents fall back to the launcher URL.
    assert reg.get("deal-scout").base_url().endswith(":8766")


def test_registry_describe_and_catalog():
    reg = build_registry()
    desc = reg.describe()
    assert "deal-scout" in desc and "Actions:" in desc
    cat = reg.to_catalog()
    assert isinstance(cat, list) and cat[0]["slug"]


def test_registry_resolve_action_falls_back_to_default():
    reg = build_registry()
    agent = reg.get("deal-scout")
    assert agent.resolve_action(None)["action"] == agent.default_action
    assert agent.resolve_action("score")["route"] == "/pipeline/score"
    assert agent.resolve_action("nope") is None


def test_stub_invoker_records_and_fires_nothing():
    reg = build_registry()
    inv = StubInvoker()
    res = inv.invoke(reg.get("ghl-agent"), action="capture", payload={"x": 1})
    assert res["ok"] and res["stub"]
    assert inv.calls[0]["agent"] == "ghl-agent"


# ---------------------------------------------------------------------------
# Dispatch brain — heuristic + LLM planner (scripted, offline)
# ---------------------------------------------------------------------------

def test_heuristic_planner_routes_deal_goal():
    reg = build_registry()
    plan = HeuristicPlanner(reg).plan("Find and score the best acquisition deal")
    assert plan["steps"] and plan["steps"][0]["agent"] == "deal-scout"


def test_heuristic_planner_unmatched_goal_is_empty():
    reg = build_registry()
    plan = HeuristicPlanner(reg).plan("xyzzy nonsense with no lobe")
    assert plan["steps"] == []


def test_build_planner_offline_is_heuristic():
    reg = build_registry()
    assert isinstance(build_planner(reg, offline=True), HeuristicPlanner)


def test_llm_planner_parses_and_validates_plan():
    reg = build_registry()
    client = _ScriptedClient(
        '{"steps": [{"agent": "content-engine", "action": "generate", '
        '"payload": {"topic": "x"}, "rationale": "make a draft"}], '
        '"rationale": "content goal"}')
    plan = LLMPlanner(reg, client=client).plan("write a post")
    assert plan["planner"] == "llm"
    assert plan["steps"][0]["agent"] == "content-engine"


def test_llm_planner_drops_hallucinated_agent_and_falls_back():
    reg = build_registry()
    client = _ScriptedClient(
        '{"steps": [{"agent": "not-a-real-agent", "action": "boom"}]}')
    plan = LLMPlanner(reg, client=client).plan("write a post")
    # No valid steps survive validation -> heuristic fallback plans it.
    assert plan["planner"] == "heuristic"


def test_llm_planner_bad_json_falls_back():
    reg = build_registry()
    plan = LLMPlanner(reg, client=_ScriptedClient("not json at all")).plan(
        "score a deal")
    assert plan["planner"] == "heuristic"
    assert plan["steps"][0]["agent"] == "deal-scout"


# ---------------------------------------------------------------------------
# dispatch_goal — plan, invoke via registry, log to ledger
# ---------------------------------------------------------------------------

def test_dispatch_goal_invokes_and_logs():
    db = _new_db()
    reg = build_registry()
    inv = StubInvoker()
    state = StubStateLedgerClient()
    planner = HeuristicPlanner(reg)
    svc = DiracatronService(db_path=db, sources=[StubSource([])],
                            dispatcher=StubDispatcher(), state=state,
                            registry=reg, planner=planner, invoker=inv,
                            offline=True)
    res = svc.dispatch_goal("score the best acquisition deal")
    assert res["ok"] is True
    assert res["results"][0]["agent"] == "deal-scout"
    assert inv.calls and inv.calls[0]["agent"] == "deal-scout"
    assert any(e["event_type"] == "triage_decision" for e in state.events)
    assert any(e["event_type"] == "triage_dispatch" for e in state.events)
    assert store.list_dispatches(path=db)


def test_dispatch_goal_empty_is_rejected():
    assert _svc(_new_db()).dispatch_goal("   ")["ok"] is False


# ---------------------------------------------------------------------------
# deal-scout source — reads scored+gated open doors from its SQLite DB
# ---------------------------------------------------------------------------

def _seed_deal_db() -> str:
    import sqlite3
    fd, path = tempfile.mkstemp(prefix="dealscout_test_", suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE raw_deals (id TEXT PRIMARY KEY, source TEXT, "
                 "name TEXT, url TEXT, asking_price REAL, monthly_net REAL, "
                 "market_status TEXT, is_closed INTEGER)")
    conn.execute("CREATE TABLE scored_deals (raw_deal_id TEXT, overall_score REAL, "
                 "gate_reason TEXT, buy_vs_build_recommendation TEXT, "
                 "buy_vs_build_rationale TEXT, build_feasibility TEXT, "
                 "moat_build_years REAL, us_eligible INTEGER)")
    conn.execute("INSERT INTO raw_deals VALUES ('d1','flippa','Acme SaaS','u',100000,5000,'available',0)")
    conn.execute("INSERT INTO scored_deals VALUES ('d1',8.5,'gate ok','buy','cashflows','high',1.0,1)")
    # Below-threshold + ineligible + closed rows must be filtered out.
    conn.execute("INSERT INTO raw_deals VALUES ('d2','flippa','Weak','u',1,1,'available',0)")
    conn.execute("INSERT INTO scored_deals VALUES ('d2',2.0,'','build','','low',5,1)")
    conn.execute("INSERT INTO raw_deals VALUES ('d3','flippa','Sold','u',1,1,'sold',1)")
    conn.execute("INSERT INTO scored_deals VALUES ('d3',9.0,'','buy','','high',1,1)")
    conn.commit()
    conn.close()
    return path


def test_deal_source_lifts_scored_gated_open_doors():
    path = _seed_deal_db()
    try:
        cands = DealScoutSource(db_path=path, min_score=5.0).candidates()
    finally:
        os.unlink(path)
    ids = [c["entity_id"] for c in cands]
    assert ids == ["d1"]  # only the high-scoring, eligible, available door
    assert cands[0]["kind"] == diracatron.KIND_DEAL_SCORE
    assert cands[0]["payload"]["buy_vs_build"] == "buy"
    assert cands[0]["payload"]["score"] == 8.5


def test_deal_source_missing_db_is_empty():
    assert DealScoutSource(db_path="/no/such/file.db").candidates() == []


def test_market_signal_source_from_literal():
    src = MarketSignalSource(signals=[{"summary": "AI wrapper churn play",
                                        "urgent": True, "revenue_path": "arbitrage"}])
    cands = src.candidates()
    assert cands[0]["kind"] == diracatron.KIND_REVENUE_LEAK
    assert cands[0]["payload"]["urgent"] is True


# ---------------------------------------------------------------------------
# digest — prioritized stack-rank of open doors
# ---------------------------------------------------------------------------

def test_digest_stack_ranks_open_doors():
    db = _new_db()
    svc = _svc(db)
    out = svc.digest(top=3)
    assert out["open"] == 6
    assert out["count"] == 3
    assert "stack-rank" in out["digest"]
    # Highest-priority kind (broker reply) heads the digest.
    assert out["items"][0]["kind"] == diracatron.KIND_BROKER_REPLY


def test_digest_emits_to_ledger():
    db = _new_db()
    state = StubStateLedgerClient()
    _svc(db, state=state).digest(top=5)
    assert any(e["event_type"] == "triage_digest" for e in state.events)


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
