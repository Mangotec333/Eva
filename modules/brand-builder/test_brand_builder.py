"""
EVA Brand-Builder — offline test suite (mocked eva-state, temp store, zero
network). NOTHING real is ever emitted or posted: the state client is a stub and
all data lives in a throwaway ``EVA_BRAND_DIR``.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module runs:

  python modules/brand-builder/test_brand_builder.py
  (or)  cd modules/brand-builder && python test_brand_builder.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force offline + a throwaway data dir BEFORE importing the modules.
os.environ["EVA_BRAND_OFFLINE"] = "1"
_TMP = tempfile.mkdtemp(prefix="brand_builder_test_")
os.environ["EVA_BRAND_DIR"] = _TMP

import blueprint as blueprint_mod  # noqa: E402
import personas as personas_mod  # noqa: E402
import planner  # noqa: E402
import store  # noqa: E402
from loop import RefreshLoop  # noqa: E402
from service import BrandBuilderService  # noqa: E402
from state_client import StubStateLedgerClient  # noqa: E402

SEED_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "seed", "brand_blueprint_eva_growth_agency.md")

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {('- ' + detail) if detail else ''}")


def fresh_service() -> BrandBuilderService:
    """A service with a stub ledger over an isolated throwaway store dir."""
    os.environ["EVA_BRAND_DIR"] = tempfile.mkdtemp(prefix="brand_svc_")
    return BrandBuilderService(state=StubStateLedgerClient(), offline=True)


# ---------------------------------------------------------------------------
# 1. blueprint parse from the seed md
# ---------------------------------------------------------------------------

def test_blueprint_parse():
    print("test_blueprint_parse")
    pipeline, bp = blueprint_mod.parse_file(SEED_MD, "eva-growth-agency")

    check("category parsed",
          "acquisition sourcing" in bp["category"].lower(), bp["category"])
    check("blueprint_version is ISO date", bp["blueprint_version"] == "2026-07-16",
          bp["blueprint_version"])
    check("audience segments", len(bp["audience"]["segments"]) == 5,
          str(len(bp["audience"]["segments"])))
    check("market_patterns present", len(bp["market_patterns"]) >= 5,
          str(len(bp["market_patterns"])))
    mp = bp["market_patterns"][0]
    check("market_pattern has date", bool(mp["date"]), mp["date"])
    check("market_pattern has source_url", mp["source_url"].startswith("http"),
          mp["source_url"])
    check("market_pattern confidence in band", mp["confidence"] in ("high", "med", "low"),
          mp["confidence"])
    check("channels parsed", len(bp["channels"]) >= 5, str(len(bp["channels"])))
    check("LinkedIn is a channel",
          any("LinkedIn" in c["channel"] for c in bp["channels"]))
    check("content_archetypes parsed", len(bp["content_archetypes"]) == 6,
          str(len(bp["content_archetypes"])))
    check("authority_signals parsed", len(bp["authority_signals"]) >= 5,
          str(len(bp["authority_signals"])))
    check("awareness_loops have hooks",
          bool(bp["awareness_loops"]) and bool(bp["awareness_loops"][0]["hook"]))
    check("cadence has X daily",
          any("daily" in v.lower() for v in bp["cadence"].values()))
    check("cta_ladder parsed", len(bp["cta_ladder"]) == 5, str(len(bp["cta_ladder"])))
    check("do_not_say parsed", len(bp["do_not_say"]) >= 5, str(len(bp["do_not_say"])))
    check("kpis parsed", len(bp["kpis"]) >= 10, str(len(bp["kpis"])))

    # derived pipeline
    check("pipeline id", pipeline["pipeline_id"] == "eva-growth-agency")
    check("pipeline approval_required true", pipeline["approval_required"] is True)
    check("pipeline has cta", bool(pipeline["cta"]))
    check("pipeline pillars from archetypes", len(pipeline["content_pillars"]) == 6)
    check("pipeline target_audience", len(pipeline["target_audience"]) == 5)


# ---------------------------------------------------------------------------
# 2. seed → pipeline + blueprint + personas persisted
# ---------------------------------------------------------------------------

def test_seed_and_load():
    print("test_seed_and_load")
    svc = fresh_service()
    res = svc.seed(md_path=SEED_MD)
    check("seed ok", res["ok"] is True)

    p = svc.get_pipeline("eva-growth-agency")
    check("pipeline loaded from store", p is not None and p["pipeline_id"] == "eva-growth-agency")
    b = svc.get_blueprint(p["category"])
    check("blueprint loaded from store", b is not None and len(b["market_patterns"]) >= 5)

    personas = store.list_personas()
    names = {pp["name"] for pp in personas}
    check("three personas persisted", names == set(personas_mod.PERSONA_NAMES), str(names))
    for pp in personas:
        check(f"persona {pp['name']} shape",
              all(k in pp for k in ("focus", "hooks", "archetypes", "channels", "tone")))

    # seed emitted a brand_pipeline_seeded event
    check("seed emitted event",
          any(e["event_type"] == "brand_pipeline_seeded" for e in svc.state.events))


# ---------------------------------------------------------------------------
# 3. plan generation
# ---------------------------------------------------------------------------

def test_plan_generation():
    print("test_plan_generation")
    svc = fresh_service()
    svc.seed(md_path=SEED_MD)
    plan = svc.plan(pipeline_id="eva-growth-agency", timeframe="week",
                    start_date="2026-07-20")
    check("plan ok", plan["ok"] is True)
    check("plan has briefs", plan["count"] >= 10, str(plan["count"]))
    check("X daily → 7 briefs", plan["by_channel"].get("X (Twitter)") == 7,
          str(plan["by_channel"]))
    check("LinkedIn 3x/week", plan["by_channel"].get("LinkedIn") == 3,
          str(plan["by_channel"]))
    check("Newsletter weekly", plan["by_channel"].get("Newsletter") == 1,
          str(plan["by_channel"]))

    b = plan["briefs"][0]
    for field in ("brief_id", "channel", "archetype", "persona", "hook", "cta",
                  "voice_rules", "do_not_say", "scheduled_day"):
        check(f"brief has {field}", field in b and b[field] != "" or field in ("voice_rules", "do_not_say"))
    check("brief approval_required true", b["approval_required"] is True)
    check("brief persisted", store.get_brief(b["brief_id"]) is not None)

    # two-week plan has ~2x briefs
    svc2 = fresh_service()
    svc2.seed(md_path=SEED_MD)
    plan2 = svc2.plan(pipeline_id="eva-growth-agency", timeframe="2w",
                      start_date="2026-07-20")
    check("2-week plan doubles", plan2["count"] == plan["count"] * 2,
          f"{plan2['count']} vs {plan['count']}")


# ---------------------------------------------------------------------------
# 4. brief emission (queue → brand_brief_created)
# ---------------------------------------------------------------------------

def test_brief_emission():
    print("test_brief_emission")
    svc = fresh_service()
    svc.seed(md_path=SEED_MD)
    plan = svc.plan(pipeline_id="eva-growth-agency", start_date="2026-07-20")
    n = plan["count"]

    q = svc.queue(pipeline_id="eva-growth-agency")
    check("queued all pending", q["queued"] == n, f"{q['queued']} vs {n}")

    events = [e for e in svc.state.events if e["event_type"] == "brand_brief_created"]
    check("emitted one event per brief", len(events) == n, f"{len(events)} vs {n}")
    ev = events[0]
    check("event payload has channel", bool(ev["payload"].get("channel")))
    check("event payload has cta", bool(ev["payload"].get("cta")))
    check("event payload carries do_not_say", "do_not_say" in ev["payload"])
    check("event approval_required true", ev["payload"].get("approval_required") is True)

    # briefs now marked queued, none pending
    check("no pending left", len(svc.list_briefs(status=store.STATUS_PENDING)) == 0)
    check("all queued", len(svc.list_briefs(status=store.STATUS_QUEUED)) == n)

    # re-queue is a no-op (nothing pending)
    q2 = svc.queue(pipeline_id="eva-growth-agency")
    check("re-queue emits nothing", q2["queued"] == 0)


# ---------------------------------------------------------------------------
# 5. persona selection
# ---------------------------------------------------------------------------

def test_persona_selection():
    print("test_persona_selection")
    check("teardown → awareness",
          personas_mod.select_persona("Deal Teardowns") == "awareness_persona")
    check("contrarian → awareness",
          personas_mod.select_persona("Contrarian Thesis") == "awareness_persona")
    check("data → authority",
          personas_mod.select_persona("Data/Proof Posts") == "authority_persona")
    check("framework → authority",
          personas_mod.select_persona("Frameworks") == "authority_persona")
    check("build-in-public → brand",
          personas_mod.select_persona("Build-in-Public") == "brand_persona")
    check("founder lessons → brand",
          personas_mod.select_persona("Founder Lessons") == "brand_persona")
    check("unknown → authority default",
          personas_mod.select_persona("Something Else") == "authority_persona")


# ---------------------------------------------------------------------------
# 6. offline mode (mocked plans/blueprints without seeding)
# ---------------------------------------------------------------------------

def test_offline_mode():
    print("test_offline_mode")
    # fresh temp dir, nothing seeded
    prev = os.environ["EVA_BRAND_DIR"]
    os.environ["EVA_BRAND_DIR"] = tempfile.mkdtemp(prefix="brand_offline_")
    try:
        svc = fresh_service()
        check("offline flag set", svc.offline is True)
        p = svc.get_pipeline("eva-growth-agency")
        check("offline mock pipeline", p is not None and p["pipeline_id"] == "eva-growth-agency")
        pls = svc.list_pipelines()
        check("offline list returns mock", len(pls) >= 1)
        b = svc.get_blueprint("mock-category")
        check("offline mock blueprint", b is not None and "cadence" in b)
        plan = svc.plan(pipeline_id="eva-growth-agency", start_date="2026-07-20")
        check("offline plan generates briefs", plan["ok"] and plan["count"] >= 1)
        # stub client — never hit network
        check("state client is stub", isinstance(svc.state, StubStateLedgerClient))
    finally:
        os.environ["EVA_BRAND_DIR"] = prev


# ---------------------------------------------------------------------------
# 7. stale-blueprint detection
# ---------------------------------------------------------------------------

def test_stale_detection():
    print("test_stale_detection")
    svc = fresh_service()
    today = date(2026, 7, 16)
    check("fresh version not stale",
          svc.is_stale("2026-07-16", now=today) is False)
    check("6-day-old not stale",
          svc.is_stale("2026-07-10", now=today) is False)
    check("8-day-old is stale",
          svc.is_stale("2026-07-08", now=today) is True)
    check("empty version is stale", svc.is_stale("", now=today) is True)
    check("garbage version is stale", svc.is_stale("not-a-date", now=today) is True)


def test_stale_refresh_emits():
    print("test_stale_refresh_emits")
    # seed a blueprint then age it, run refresh → expect brand_blueprint_stale
    d = tempfile.mkdtemp(prefix="brand_stale_")
    prev = os.environ["EVA_BRAND_DIR"]
    os.environ["EVA_BRAND_DIR"] = d
    try:
        svc = fresh_service()
        svc.seed(md_path=SEED_MD)
        # force the stored blueprint to be old
        p = svc.get_pipeline("eva-growth-agency")
        b = store.get_blueprint(p["category"])
        b["blueprint_version"] = "2020-01-01"
        store.save_blueprint(p["category"], b)

        svc.state.events.clear()
        res = svc.refresh()
        check("refresh reports stale", p["category"] in res["stale"], str(res["stale"]))
        check("refresh emitted stale event",
              any(e["event_type"] == "brand_blueprint_stale" for e in svc.state.events))

        # a fresh blueprint should not be flagged
        b["blueprint_version"] = date.today().isoformat()
        store.save_blueprint(p["category"], b)
        svc.state.events.clear()
        res2 = svc.refresh()
        check("fresh blueprint not stale", p["category"] not in res2["stale"])
        check("no stale event for fresh",
              not any(e["event_type"] == "brand_blueprint_stale" for e in svc.state.events))
    finally:
        os.environ["EVA_BRAND_DIR"] = prev


# ---------------------------------------------------------------------------
# 8. refresh loop is offline-safe (does not spawn a thread)
# ---------------------------------------------------------------------------

def test_loop_offline_safe():
    print("test_loop_offline_safe")
    svc = fresh_service()
    loop = RefreshLoop(svc, offline=True)
    started = loop.start()
    check("offline loop does not start", started is False)
    check("offline loop not running", loop.is_running() is False)
    # fire() still works directly and never raises
    out = loop.fire()
    check("fire returns ok", out.get("ok") is True)


def main() -> int:
    for fn in (test_blueprint_parse, test_seed_and_load, test_plan_generation,
               test_brief_emission, test_persona_selection, test_offline_mode,
               test_stale_detection, test_stale_refresh_emits, test_loop_offline_safe):
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
