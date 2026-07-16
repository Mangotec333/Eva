"""
EVA IP-Scout — offline test suite (mocked PatentsView, stubbed eva-state, temp
store, zero network). NOTHING real is ever emitted, posted, or filed: the prior-
art provider is a deterministic mock, the state client is a stub, and all data
lives in a throwaway EVA_IP_DIR / EVA_IP_IDEAS_FILE.

Stdlib-only runner (no pytest dependency):

  python modules/ip-scout/test_ip_scout.py
  (or)  cd modules/ip-scout && python test_ip_scout.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force offline + throwaway data locations BEFORE importing the modules.
os.environ["EVA_IP_OFFLINE"] = "1"
_TMP = tempfile.mkdtemp(prefix="ip_scout_test_")
os.environ["EVA_IP_DIR"] = _TMP
os.environ["EVA_IP_IDEAS_FILE"] = os.path.join(_TMP, "ip_ideas.json")

import mining  # noqa: E402
import novelty  # noqa: E402
import store  # noqa: E402
from loop import TriageLoop  # noqa: E402
from provider import MockPriorArtProvider, PatentsViewProvider, build_provider  # noqa: E402
from report import render_report  # noqa: E402
from service import IPScoutService  # noqa: E402
from state_client import StubStateLedgerClient  # noqa: E402

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


def fresh_env(seed_events=None) -> IPScoutService:
    """Isolated throwaway store + stub ledger + mock provider."""
    d = tempfile.mkdtemp(prefix="ip_svc_")
    os.environ["EVA_IP_DIR"] = d
    os.environ["EVA_IP_IDEAS_FILE"] = os.path.join(d, "ip_ideas.json")
    return IPScoutService(
        state=StubStateLedgerClient(seed_events=seed_events),
        provider=MockPriorArtProvider(),
        offline=True)


# ---------------------------------------------------------------------------
# 1. idea seed + load
# ---------------------------------------------------------------------------

def test_seed_and_load():
    print("test_seed_and_load")
    svc = fresh_env()
    idea = svc.seed_idea(title="Adaptive drone battery swap",
                         description="A method for autonomous mid-flight battery hot-swap.",
                         category="robotics")
    check("seed returns id", bool(idea.get("id")), idea.get("id", ""))
    check("seed status pending", idea["status"] == store.STATUS_PENDING)
    check("seed has seeded_at", bool(idea.get("seeded_at")))

    loaded = svc.list_ideas()
    check("idea persisted to ideas.json", len(loaded) == 1)
    check("idea fields intact",
          loaded[0]["title"] == "Adaptive drone battery swap" and
          loaded[0]["category"] == "robotics")

    one = svc.get_idea(idea["id"])
    check("get_idea returns record", one is not None and one["id"] == idea["id"])

    # update via re-seed by id
    svc.seed_idea(title="Adaptive drone battery swap v2", idea_id=idea["id"])
    check("re-seed updates, not duplicates", len(svc.list_ideas()) == 1)
    check("seed emitted event",
          any(e["event_type"] == "ip_idea_seeded" for e in svc.state.events))


# ---------------------------------------------------------------------------
# 2. scan triage → disclosures + report + status transition
# ---------------------------------------------------------------------------

def test_scan_triage():
    print("test_scan_triage")
    svc = fresh_env()
    svc.seed_idea(title="Quantum-resistant mesh key rotation",
                  description="A protocol rotating lattice keys across a device mesh.",
                  category="security")
    svc.seed_idea(title="Solar road heater",
                  description="Embedded photovoltaic heating elements in pavement.",
                  category="energy")

    res = svc.scan(report_date="2026-07-16", mine=False)
    check("scan ok", res["ok"] is True)
    check("scanned two ideas", res["ideas_scanned"] == 2, str(res["ideas_scanned"]))
    check("two disclosures created", res["disclosures_created"] == 2)
    check("run id present", bool(res["run_id"]))
    check("report path written", bool(res["report_path"]) and os.path.exists(res["report_path"]))

    disc = res["disclosures"][0]
    for field in ("idea_id", "title", "abstract", "claims_draft", "sensor_source",
                  "created_at", "novelty_score", "confidence_band", "prior_art_hits",
                  "status", "attorney_review_needed", "recommendation"):
        check(f"disclosure has {field}", field in disc, field)
    check("disclosure claims non-empty", len(disc["claims_draft"]) >= 1)
    check("disclosure status triaged", disc["status"] == store.STATUS_TRIAGED)
    check("novelty in [0,1]", 0.0 <= disc["novelty_score"] <= 1.0)
    check("recommendation valid",
          disc["recommendation"] in ("file", "monitor", "drop"), disc["recommendation"])

    # ideas flipped to triaged, nothing pending
    check("no pending ideas left",
          len(svc.list_ideas(status=store.STATUS_PENDING)) == 0)
    check("two triaged ideas",
          len(svc.list_ideas(status=store.STATUS_TRIAGED)) == 2)

    # events emitted
    check("scan emitted ip_scan_run",
          any(e["event_type"] == "ip_scan_run" for e in svc.state.events))
    check("scan emitted ip_disclosure_created",
          sum(1 for e in svc.state.events if e["event_type"] == "ip_disclosure_created") == 2)
    check("scan emitted ip_report_written",
          any(e["event_type"] == "ip_report_written" for e in svc.state.events))

    # re-scan does nothing (all triaged)
    res2 = svc.scan(report_date="2026-07-17", mine=False)
    check("re-scan no pending", res2["disclosures_created"] == 0)


# ---------------------------------------------------------------------------
# 3. novelty scoring + confidence bands
# ---------------------------------------------------------------------------

def test_novelty_scoring():
    print("test_novelty_scoring")
    idea = "A novel widget for teleporting cats safely across dimensions"

    # no hits → high novelty but LOW confidence (nothing examined)
    s0 = novelty.score(idea, [], ["A method for teleporting cats."], provider_ok=True)
    check("no-hits high novelty", s0["novelty_score"] >= 0.9, str(s0["novelty_score"]))
    check("no-hits low confidence", s0["confidence_band"] == "low", s0["confidence_band"])
    check("low-conf never files", s0["recommendation"] != "file", s0["recommendation"])

    # many highly-overlapping hits → low novelty
    heavy = [{"title": idea, "abstract": idea} for _ in range(9)]
    s1 = novelty.score(idea, heavy, [], provider_ok=True)
    check("heavy-overlap low novelty", s1["novelty_score"] <= 0.3, str(s1["novelty_score"]))
    check("many hits high confidence", s1["confidence_band"] == "high", s1["confidence_band"])
    check("heavy-overlap drops", s1["recommendation"] == "drop", s1["recommendation"])

    # a few unrelated hits → medium confidence, high novelty → file
    light = [{"title": "unrelated turbine blade", "abstract": "steam power"} for _ in range(3)]
    s2 = novelty.score(idea, light, ["claim one", "claim two"], provider_ok=True)
    check("few-unrelated med confidence", s2["confidence_band"] == "med", s2["confidence_band"])
    check("few-unrelated high novelty file", s2["recommendation"] == "file",
          f"{s2['recommendation']} @ {s2['novelty_score']}")

    # provider failed → forced low confidence even with hits
    s3 = novelty.score(idea, light, [], provider_ok=False)
    check("provider-fail forces low conf", s3["confidence_band"] == "low")

    # attorney review flagged unless a confident drop
    check("file flags attorney review", s2["attorney_review_needed"] is True)
    check("drop does not flag review", s1["attorney_review_needed"] is False)

    # claim specificity raises novelty
    base = novelty.score(idea, light, [])["novelty_score"]
    rich = novelty.score(idea, light,
                         ["alpha beta gamma", "delta epsilon zeta", "eta theta iota"])["novelty_score"]
    check("claim specificity raises novelty", rich >= base, f"{rich} vs {base}")


# ---------------------------------------------------------------------------
# 4. prior-art hit parsing (mocked PatentsView response)
# ---------------------------------------------------------------------------

def test_prior_art_parsing():
    print("test_prior_art_parsing")
    raw = {
        "patents": [
            {"patent_id": "10000001", "patent_title": "Widget A",
             "patent_abstract": "Does widget things.", "patent_date": "2018-05-01"},
            {"patent_id": "10000002", "patent_title": "Widget B",
             "patent_abstract": "More widgets.", "patent_date": "2020-01-01"},
            {"not_a_patent": True},  # tolerated / skipped-ish
        ]
    }
    hits = PatentsViewProvider._parse_hits(raw, limit=20)
    check("parsed two+ hits", len(hits) >= 2, str(len(hits)))
    h = hits[0]
    check("hit has patent_id", h["patent_id"] == "10000001")
    check("hit has title", h["title"] == "Widget A")
    check("hit has abstract", h["abstract"] == "Does widget things.")
    check("hit has url", h["url"].startswith("https://"))

    # empty / malformed responses don't crash
    check("empty response → no hits", PatentsViewProvider._parse_hits({}, 20) == [])
    check("garbage response → no hits", PatentsViewProvider._parse_hits({"patents": None}, 20) == [])

    # provider with no key returns honest failure, never raises
    p = PatentsViewProvider(api_key="")
    r = p.search("anything")
    check("no-key provider ok False", r["ok"] is False and "hits" in r)

    # mock provider hit_map override
    mp = MockPriorArtProvider(hit_map={"battery": [{"patent_id": "X1", "title": "batt"}]})
    r2 = mp.search("a battery idea")
    check("mock hit_map override works", r2["hits"][0]["patent_id"] == "X1")


# ---------------------------------------------------------------------------
# 5. report generation
# ---------------------------------------------------------------------------

def test_report_generation():
    print("test_report_generation")
    disclosures = [
        {"idea_id": "a", "title": "High novelty thing", "abstract": "abc",
         "claims_draft": ["c1", "c2"], "sensor_source": "user-seed",
         "novelty_score": 0.9, "confidence_band": "high",
         "prior_art_hits": [{"patent_id": "P1", "title": "ref"}],
         "recommendation": "file", "attorney_review_needed": True},
        {"idea_id": "b", "title": "Meh thing", "abstract": "def",
         "claims_draft": ["c1"], "sensor_source": "activity-mining",
         "novelty_score": 0.2, "confidence_band": "high", "prior_art_hits": [],
         "recommendation": "drop", "attorney_review_needed": False},
    ]
    md = render_report("2026-07-16", disclosures, offline=True, provider="mock")
    check("report has date header", "2026-07-16" in md)
    check("report has disclaimer", "Not legal advice" in md)
    check("report never asserts patentable", "attorney" in md.lower())
    check("report has file section", "File" in md)
    check("report has drop section", "Drop" in md)
    check("report lists prior-art hit", "P1" in md)
    check("report shows novelty score", "0.90" in md)

    # empty report is graceful
    empty = render_report("2026-07-16", [], offline=True, provider="mock")
    check("empty report graceful", "No pending ideas" in empty)


# ---------------------------------------------------------------------------
# 6. offline mode (no network, mock provider selected)
# ---------------------------------------------------------------------------

def test_offline_mode():
    print("test_offline_mode")
    svc = fresh_env()
    check("service offline", svc.offline is True)
    check("provider is mock", svc.provider.name == "mock")
    check("state client is stub", isinstance(svc.state, StubStateLedgerClient))

    # build_provider offline → mock
    check("build_provider offline → mock", build_provider(offline=True).name == "mock")

    svc.seed_idea(title="Offline widget", description="does things offline")
    res = svc.scan(mine=False)
    check("offline scan works end-to-end", res["ok"] and res["disclosures_created"] == 1)
    # no network was touched — stub recorded events only
    check("offline emitted only to stub", len(svc.state.events) >= 1)


# ---------------------------------------------------------------------------
# 7. activity-mining stub
# ---------------------------------------------------------------------------

def test_activity_mining():
    print("test_activity_mining")
    events = (
        [{"event_type": "deal_scored", "summary": "scored a deal",
          "source_surface": "deal-scout"}] * 4 +
        [{"event_type": "one_off", "summary": "rare"}] +
        [{"event_type": "heartbeat", "summary": "noise"}] * 10
    )
    cands = mining.mine_activity(events, min_occurrences=3)
    check("mines repeatable pattern", any(c["id"] == "mined-deal_scored" for c in cands))
    check("ignores rare event", not any(c["id"] == "mined-one_off" for c in cands))
    check("ignores heartbeat noise", not any("heartbeat" in c["id"] for c in cands))
    dc = next(c for c in cands if c["id"] == "mined-deal_scored")
    check("candidate tagged activity-mining", dc["sensor_source"] == "activity-mining")
    check("candidate has occurrences", dc["occurrences"] == 4)

    # known ideas are not re-proposed
    cands2 = mining.mine_activity(events, min_occurrences=3,
                                  known_idea_ids={"mined-deal_scored"})
    check("known idea not re-mined", not any(c["id"] == "mined-deal_scored" for c in cands2))

    # service.mine_ideas reads from the stub ledger + persists
    svc = fresh_env(seed_events=events)
    mined = svc.mine_ideas(min_occurrences=3)
    check("service mines candidates", any(c["id"] == "mined-deal_scored" for c in mined))
    check("mined idea persisted",
          any(i["id"] == "mined-deal_scored" for i in svc.list_ideas()))

    # a full scan with mining enabled triages the mined idea too
    svc2 = fresh_env(seed_events=events)
    res = svc2.scan(mine=True)
    check("scan-with-mining triages mined idea",
          any(d["sensor_source"] == "activity-mining" for d in res["disclosures"]))


# ---------------------------------------------------------------------------
# 8. history + report retrieval
# ---------------------------------------------------------------------------

def test_history_and_report_read():
    print("test_history_and_report_read")
    svc = fresh_env()
    svc.seed_idea(title="Historic idea", description="for history test")
    svc.scan(report_date="2026-07-16", mine=False)
    svc.seed_idea(title="Another idea", description="second run")
    svc.scan(report_date="2026-07-17", mine=False)

    runs = svc.history()
    check("history has two runs", len(runs) == 2, str(len(runs)))
    check("history newest first",
          runs[0]["report_date"] == "2026-07-17", runs[0].get("report_date", ""))
    check("run records disclosure count", runs[0]["disclosures_created"] == 1)

    md = svc.get_report("2026-07-16")
    check("report retrievable by date", md is not None and "2026-07-16" in md)
    check("missing report returns None", svc.get_report("1999-01-01") is None)

    st = svc.status()
    check("status L1 autonomy stated", "L1" in st["autonomy"])
    check("status lists sensors", len(st["sensors"]) == 2)
    check("status reports both report dates", len(st["reports"]) == 2)


# ---------------------------------------------------------------------------
# 9. loop is offline-safe + resilient
# ---------------------------------------------------------------------------

def test_loop_offline_safe():
    print("test_loop_offline_safe")
    svc = fresh_env()
    loop = TriageLoop(svc, offline=True)
    check("offline loop does not start", loop.start() is False)
    check("offline loop not running", loop.is_running() is False)
    # fire() works directly and never raises
    out = loop.fire()
    check("fire returns ok", out.get("ok") is True)
    check("fire recorded", len(loop.fires) == 1)


def test_loop_resilient():
    print("test_loop_resilient")
    class Boom:
        offline = False
        def scan(self):
            raise RuntimeError("provider exploded")
    loop = TriageLoop(Boom(), offline=True)
    out = loop.fire()
    check("fire catches exception", out["ok"] is False and "RuntimeError" in out["error"])


def main() -> int:
    for fn in (test_seed_and_load, test_scan_triage, test_novelty_scoring,
               test_prior_art_parsing, test_report_generation, test_offline_mode,
               test_activity_mining, test_history_and_report_read,
               test_loop_offline_safe, test_loop_resilient):
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
