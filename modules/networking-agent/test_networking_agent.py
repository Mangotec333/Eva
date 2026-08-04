"""
Offline test suite for the EVA Networking-Agent module.

No network, no external deps beyond the standard library + pydantic. Runs two
ways:

    python test_networking_agent.py    # standalone runner, prints PASS/FAIL
    pytest test_networking_agent.py     # if pytest is installed

Every test builds a fresh service backed by a throwaway SQLite file and an
offline (stub) state client, so runs are fully isolated and network-free.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import scoring
from discovery import ManualSeedProvider, parse_seed
from state_client import StubStateLedgerClient
from store import OUTCOME_SIGNALS, Store
from service import NetworkingAgentService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> NetworkingAgentService:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-networking-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return NetworkingAgentService(store=Store(path),
                                  state=StubStateLedgerClient(), offline=True)


def _seed_rows() -> list[dict]:
    return [
        {"platform": "reddit", "name": "r/SearchFunds",
         "url": "https://reddit.com/r/SearchFunds", "member_count": 12000,
         "activity_score": 0.6, "topical_fit_score": 0.95, "access_type": "public"},
        {"platform": "slack", "name": "ETA Slack",
         "url": "https://example.com/eta", "member_count": 4500,
         "activity_score": 0.75, "topical_fit_score": 0.9,
         "access_type": "invite_only"},
    ]


def _discover(svc) -> list[dict]:
    res = svc.discover("eva_growth_agency", _seed_rows())
    assert res["ok"], res
    return res["created"]


# ---------------------------------------------------------------------------
# Scoring math
# ---------------------------------------------------------------------------

def test_scoring_weights_sum_to_one():
    assert abs(scoring.W_TOPICAL + scoring.W_ACTIVITY
               + scoring.W_MEMBERS + scoring.W_ACCESS - 1.0) < 1e-9


def test_scoring_deterministic_and_bounded():
    g = {"member_count": 12000, "activity_score": 0.6,
         "topical_fit_score": 0.95, "access_type": "public"}
    a = scoring.score_group(g)
    b = scoring.score_group(g)
    assert a == b                    # deterministic
    assert 0.0 <= a["score"] <= 1.0  # bounded


def test_scoring_expected_value():
    # public room, perfect topical + activity, at member saturation → all 1.0.
    g = {"member_count": scoring.MEMBER_SATURATION, "activity_score": 1.0,
         "topical_fit_score": 1.0, "access_type": "public"}
    out = scoring.score_group(g)
    assert out["score"] == 1.0
    assert out["confidence"] == "high"


def test_scoring_clamps_out_of_range_inputs():
    g = {"member_count": -5, "activity_score": 5, "topical_fit_score": -2,
         "access_type": "public"}
    out = scoring.score_group(g)
    assert out["components"]["activity"] == 1.0
    assert out["components"]["topical_fit"] == 0.0
    assert out["components"]["member_norm"] == 0.0
    # only access + activity present → not high confidence.
    assert out["confidence"] in ("low", "med")


def test_scoring_access_difficulty_penalises():
    base = {"member_count": 10000, "activity_score": 0.5, "topical_fit_score": 0.5}
    public = scoring.score_group({**base, "access_type": "public"})["score"]
    invite = scoring.score_group({**base, "access_type": "invite_only"})["score"]
    assert public > invite


# ---------------------------------------------------------------------------
# Store CRUD + migration idempotency + append-only ledger
# ---------------------------------------------------------------------------

def test_store_init_is_idempotent():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(path)
    s = Store(path)
    s.init_db(); s.init_db()  # re-running the migration is a no-op
    weights = s.get_weights()
    assert set(weights) == set(OUTCOME_SIGNALS)
    # weights unchanged by re-init (INSERT OR IGNORE).
    assert weights["meeting_booked"] == OUTCOME_SIGNALS["meeting_booked"]


def test_store_group_crud():
    s = _fresh_service().store
    g = s.insert_group({"name": "X", "platform": "reddit", "venture_tag": "shopify"})
    assert s.get_group(g["id"])["name"] == "X"
    s.update_group(g["id"], {"status": "qualified"})
    assert s.get_group(g["id"])["status"] == "qualified"
    assert len(s.list_groups(venture="shopify")) == 1
    assert len(s.list_groups(venture="storeys")) == 0


def test_outcomes_ledger_is_append_only():
    s = _fresh_service().store
    rec = s.append_outcome("group", "g1", "joined", signal="joined")
    for sql in (f"UPDATE outcomes SET outcome='x' WHERE id='{rec['id']}'",
                f"DELETE FROM outcomes WHERE id='{rec['id']}'"):
        raised = False
        try:
            with s._connect() as conn:
                conn.execute(sql)
        except sqlite3.IntegrityError:
            raised = True
        assert raised, f"expected append-only violation for: {sql}"


# ---------------------------------------------------------------------------
# Discovery (ManualSeedProvider, offline)
# ---------------------------------------------------------------------------

def test_manual_seed_provider_parses_rows():
    rows = ManualSeedProvider().discover("shopify", _seed_rows())
    assert len(rows) == 2
    assert rows[0]["name"] == "r/SearchFunds"


def test_parse_seed_csv_and_markdown():
    csv_text = "name,platform,member_count,access_type\nFoo,reddit,100,public\n"
    md_text = ("| name | platform | member_count | access_type |\n"
               "|------|----------|--------------|-------------|\n"
               "| Bar | slack | 50 | private |\n")
    csv_rows = parse_seed(csv_text)
    md_rows = parse_seed(md_text)
    assert csv_rows[0]["name"] == "Foo" and csv_rows[0]["member_count"] == 100
    assert md_rows[0]["name"] == "Bar" and md_rows[0]["access_type"] == "private"


def test_discover_persists_scores_and_dedupes():
    svc = _fresh_service()
    created = _discover(svc)
    assert len(created) == 2
    assert all(g["score"] > 0 for g in created)
    # re-discovering the same URLs skips duplicates.
    again = svc.discover("eva_growth_agency", _seed_rows())
    assert again["created_count"] == 0 and again["skipped_count"] == 2


def test_live_providers_are_stubs():
    from discovery import RedditProvider
    res = _fresh_service().discover("shopify", None, provider="reddit")
    assert res["ok"] is False and res["code"] == "provider_not_wired"
    try:
        RedditProvider().discover("shopify")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


# ---------------------------------------------------------------------------
# Autonomy whitelist enforcement (MANDATORY)
# ---------------------------------------------------------------------------

def test_non_whitelisted_auto_action_is_rejected():
    """A content action routed through the auto path MUST be rejected."""
    svc = _fresh_service()
    g = _discover(svc)[0]
    for bad in ("post", "comment", "connection_request", "dm"):
        res = svc.auto_action(bad, g["id"])
        assert res["ok"] is False, f"{bad} should be rejected"
        assert res["code"] == "not_auto_allowed"
    # ...and the rejection is recorded on the append-only ledger.
    rejects = [o for o in svc.list_outcomes(entity_id=g["id"])
               if o["outcome"] == "auto_action_rejected"]
    assert len(rejects) == 4


def test_whitelisted_auto_action_executes_and_logs():
    svc = _fresh_service()
    g = _discover(svc)[0]
    res = svc.auto_action("join_public_group", g["id"])
    assert res["ok"] is True and res["signal"] == "joined"
    # join advances a candidate to qualified.
    assert svc.get_group(g["id"])["status"] == "qualified"
    logged = [o for o in svc.list_outcomes(entity_id=g["id"])
              if o["signal"] == "joined"]
    assert len(logged) == 1

    res2 = svc.auto_action("monitor_keyword_mention", g["id"])
    assert res2["ok"] is True and res2["signal"] == "keyword_mention_found"


# ---------------------------------------------------------------------------
# Draft → approve → send/post state machine
# ---------------------------------------------------------------------------

def test_send_blocked_before_approval():
    svc = _fresh_service()
    g = _discover(svc)[0]
    d = svc.draft("group", g["id"], "Hello group", action="comment")
    assert d["ok"] and d["draft"]["status"] == "draft"
    blocked = svc.send(d["draft"]["id"])
    assert blocked["ok"] is False and blocked["code"] == "not_approved"


def test_draft_approve_send_happy_path():
    svc = _fresh_service()
    g = _discover(svc)[0]
    d = svc.draft("group", g["id"], "A helpful, non-pitchy comment.", action="comment")
    did = d["draft"]["id"]
    appr = svc.approve(did, approved_by="founder")
    assert appr["ok"] and appr["draft"]["status"] == "approved"
    sent = svc.post(did)  # post is an alias for send
    assert sent["ok"] and sent["draft"]["status"] == "sent"
    # double-send is rejected (no longer in approved state).
    assert svc.send(did)["ok"] is False


def test_draft_requires_existing_entity():
    svc = _fresh_service()
    res = svc.draft("group", "does-not-exist", "hi")
    assert res["ok"] is False and res["code"] == "not_found"


# ---------------------------------------------------------------------------
# Directives + planning
# ---------------------------------------------------------------------------

def test_directives_cover_three_ventures():
    svc = _fresh_service()
    for v in ("eva_growth_agency", "storeys", "shopify"):
        d = svc.get_directive(v)
        assert d.get("icp") and d.get("offer") and d.get("keywords")
    assert svc.get_directive("nope").get("error")


def test_plan_returns_next_best_actions():
    svc = _fresh_service()
    _discover(svc)
    plan = svc.plan("eva_growth_agency")
    assert plan["ok"] and plan["groups"]
    nba = plan["groups"][0]["next_best_action"]
    assert nba["action"] and nba["advances_to"]


# ---------------------------------------------------------------------------
# KAIZEN reweighting
# ---------------------------------------------------------------------------

def test_kaizen_reweight_no_outcomes_keeps_base():
    svc = _fresh_service()
    res = svc.kaizen_reweight()
    assert res["ok"] and res["total_signals"] == 0
    assert res["weights"]["meeting_booked"] == OUTCOME_SIGNALS["meeting_booked"]


def test_kaizen_reweight_reinforces_prevalent_signal():
    svc = _fresh_service()
    g = _discover(svc)[0]
    # flood the ledger with a positive signal (below the weight cap so it can rise).
    for _ in range(20):
        svc.log_outcome("group", g["id"], "engaged", signal="content_engagement")
    res = svc.kaizen_reweight()
    assert res["ok"] and res["total_signals"] >= 20
    # a dominant positive signal's weight rises above its base.
    assert res["weights"]["content_engagement"] > OUTCOME_SIGNALS["content_engagement"]
    # weights persisted.
    assert svc.get_weights()["content_engagement"] == res["weights"]["content_engagement"]


def test_log_outcome_rejects_unknown_signal():
    svc = _fresh_service()
    res = svc.log_outcome("group", "g1", "weird", signal="not_a_real_signal")
    assert res["ok"] is False and res["code"] == "unknown_signal"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [v for k, v in sorted(globals().items())
            if k.startswith("test_") and callable(v)]


def main() -> int:
    passed, failed = 0, 0
    for test in _all_tests():
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
