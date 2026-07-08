"""
Offline self-test for the Cost-Gate Cascade (simplified).
=========================================================

Fully offline — no network, no API key, no pip installs beyond what the module
already uses. Exercises:

  * Gate 1 radar   — each of the 4 checks drops the right deal; a good deal passes
  * route_deal     — 7.6 => SHORTLIST, 5.9 => LOG_ONLY
  * should_second_opinion — true only for SHORTLIST
  * loop LOG_ONLY  — scored with NO brain (tokens=0), tier persisted
  * loop SHORTLIST — Claude called ONLY when second_opinion enabled + key present
                     (Noop = no key => tokens 0; Mock = "key" => tokens > 0)
  * testing mode   — open_all_gates forces full treatment on a below-threshold
                     deal AND logs a training_observation
  * radar drop     — a red-flagged deal is logged (tier=DROPPED) and NOT scored

Run:  python test_cost_gate.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
for _p in (_THIS_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import memory  # noqa: E402
from agent import DealAnalyzerAgent  # noqa: E402
from cost_gate import (  # noqa: E402
    CostTier, load_config, route_deal, should_second_opinion,
)
from models import DealV7, KnownOutcome  # noqa: E402
from radar import radar_filter  # noqa: E402
from services.remote.claude import NoopClaudeClient  # noqa: E402

# Strong SaaS + rich enrichment deterministically scores >= 7.5 (SHORTLIST);
# a bare Content site scores ~5.0 (LOG_ONLY). Anchors verified against v7.
_STRONG_ENRICHMENT = {
    "num_competitors": 3, "has_sdk_integration": True, "has_proprietary_data": True,
    "has_network_effect": True, "tam_usd": 2_000_000_000, "sam_usd": 300_000_000,
    "market_growth_rate_pct": 25, "tam_confidence_score": 85,
    "tam_source_url": "https://example.com/statista", "niche_growth_score": 80,
    "market_fragmentation_score": 70, "named_competitors": ["A", "B"],
    "estimated_market_share": 18,
}


class MockBrainClient:
    """Offline stand-in for a CONFIGURED brain (a 'key' is present).

    Conforms to the BrainClient Protocol. ``configured=True`` makes the agent
    treat it as reachable, so the second-opinion path actually fires — letting us
    prove the gate WITHOUT a network call or real key.
    """
    configured = True

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, max_tokens=1024, model=""):
        self.calls += 1
        return {
            "content": '{"qualitative_notes": "looks solid", "confidence": 0.8}',
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 120, "output_tokens": 40},
            "error": None,
        }


def _mk(name, category, monthly_net, annual_multiple, notes=""):
    ts = datetime.now(timezone.utc).isoformat()
    return DealV7(
        id=str(uuid.uuid4()), source="manual", listing_id="", url="",
        name=name, category=category, monthly_net=monthly_net,
        annual_multiple=annual_multiple, asking_price=monthly_net * annual_multiple * 12,
        age_years=6, notes=notes, discovered_at=ts, created_at=ts, updated_at=ts,
    )


def _cfg(**overrides):
    """A complete cost-gate config from defaults with test overrides applied."""
    cfg = load_config()
    for key, val in overrides.items():
        cfg[key] = val
    return cfg


def _agent(brain=None, second_opinion=False, config=None, paid_enrich_fn=None):
    db = os.path.join(tempfile.mkdtemp(prefix="eva_gate_"), "memory.db")
    return DealAnalyzerAgent(
        brain=brain or NoopClaudeClient(), db_path=db,
        second_opinion=second_opinion, config=config or load_config(),
        paid_enrich_fn=paid_enrich_fn,
    )


# ===========================================================================
# 1) GATE 1 RADAR
# ===========================================================================

def test_gate1_radar():
    print("=" * 72)
    print("1) GATE 1 RADAR — each check drops the right deal")
    print("=" * 72)
    cfg = load_config()

    good = _mk("Acme SaaS", "SaaS", 12000, 3.2, notes="clean B2B SaaS")
    passed, reasons = radar_filter(good, cfg)
    assert passed and reasons == [], (passed, reasons)
    print(f"  good deal            -> passed={passed} reasons={reasons}")

    # a) data completeness: multiple missing (dict deal, no annual_multiple)
    incomplete = {"category": "SaaS", "monthly_net": 12000, "notes": ""}
    passed, reasons = radar_filter(incomplete, cfg)
    assert not passed and any("data_completeness" in r for r in reasons), reasons
    print(f"  missing multiple     -> drop: {reasons}")

    # b) category/niche fit: not in allowed set
    bad_cat = _mk("Casino Affiliate", "Gambling", 12000, 3.0)
    passed, reasons = radar_filter(bad_cat, cfg)
    assert not passed and any("category_niche_fit" in r for r in reasons), reasons
    print(f"  bad category         -> drop: {reasons}")

    # c) price band: profit below floor
    low_profit = _mk("Tiny SaaS", "SaaS", 500, 3.0)
    passed, reasons = radar_filter(low_profit, cfg)
    assert not passed and any("price_range_band" in r and "profit" in r for r in reasons), reasons
    print(f"  profit < floor       -> drop: {reasons}")

    # c) price band: multiple above ceiling
    high_mult = _mk("Pricey SaaS", "SaaS", 12000, 8.0)
    passed, reasons = radar_filter(high_mult, cfg)
    assert not passed and any("price_range_band" in r and "multiple" in r for r in reasons), reasons
    print(f"  multiple > ceiling   -> drop: {reasons}")

    # d) red flag: declining trend in notes
    red = _mk("Fading Content", "Content", 4000, 2.5, notes="revenue declining, PBN links")
    passed, reasons = radar_filter(red, cfg)
    assert not passed and any("red_flag_screen" in r for r in reasons), reasons
    print(f"  red flags            -> drop: {reasons}")

    # d) red flag: single-customer concentration (numeric field, fail-closed)
    conc = {"category": "SaaS", "monthly_net": 12000, "annual_multiple": 3.0,
            "single_customer_pct": 65}
    passed, reasons = radar_filter(conc, cfg)
    assert not passed and any("single-customer" in r for r in reasons), reasons
    print(f"  single-customer 65%  -> drop: {reasons}")

    # radar NEVER raises — even on nonsense input it returns a tuple
    passed, reasons = radar_filter(object(), cfg)
    assert isinstance(passed, bool) and isinstance(reasons, list)
    print(f"  garbage input        -> no raise (passed={passed})")
    print("  [1] radar assertions passed.\n")


# ===========================================================================
# 2) ROUTE + SECOND-OPINION GATE
# ===========================================================================

def test_route_and_second_opinion():
    print("=" * 72)
    print("2) route_deal + should_second_opinion")
    print("=" * 72)
    cfg = load_config()

    assert route_deal(None, 7.6, cfg) is CostTier.SHORTLIST
    assert route_deal(None, 5.9, cfg) is CostTier.LOG_ONLY
    assert route_deal(None, 7.5, cfg) is CostTier.SHORTLIST, "boundary: >= is inclusive"
    print("  route_deal: 7.6->SHORTLIST, 7.5->SHORTLIST, 5.9->LOG_ONLY")

    assert should_second_opinion(None, 7.6, cfg) is True
    assert should_second_opinion(None, 5.9, cfg) is False
    print("  should_second_opinion: true only for shortlist")
    print("  [2] routing assertions passed.\n")


# ===========================================================================
# 3) LOOP — LOG_ONLY scores with NO brain (tokens=0)
# ===========================================================================

def test_log_only_no_brain():
    print("=" * 72)
    print("3) LOOP — LOG_ONLY deal scored with NO brain (tokens=0)")
    print("=" * 72)
    agent = _agent(brain=NoopClaudeClient(), second_opinion=False)
    content = _mk("Content Site — Pet Care", "Content", 3000, 2.5)
    result = agent.run_deal(content)

    assert result["dropped"] is False
    assert result["tier"] == CostTier.LOG_ONLY.value, result["tier"]
    assert result["tokens"] == 0, "LOG_ONLY must spend no brain tokens"
    assert result["deal"]["overall_score"] > 0, "deterministic core still scores"
    runs = memory.list_runs(deal_id=result["deal"]["id"], path=agent.db_path)
    assert runs and runs[0]["tokens"] == 0
    assert "LOG_ONLY" in runs[0]["notes"]
    print(f"  {content.name}: score={result['deal']['overall_score']} "
          f"tier={result['tier']} tokens={result['tokens']}")
    print("  [3] LOG_ONLY assertions passed.\n")


# ===========================================================================
# 4) LOOP — SHORTLIST calls Claude only if enabled + key present
# ===========================================================================

def test_shortlist_second_opinion_gating():
    print("=" * 72)
    print("4) LOOP — SHORTLIST second-opinion gating")
    print("=" * 72)
    strong = _mk("Strong SaaS", "SaaS", 18000, 3.5, notes="SaaS API proprietary")

    # (a) enabled but NO key (Noop) -> shortlist, but brain can't run -> tokens 0
    a = _agent(brain=NoopClaudeClient(), second_opinion=True)
    r = a.run_deal(strong, enrichment=_STRONG_ENRICHMENT)
    assert r["tier"] == CostTier.SHORTLIST.value, r["tier"]
    assert r["tokens"] == 0, "no key => no brain even on shortlist"
    assert r["gate_trace"]["second_opinion"] is False
    print(f"  enabled + NO key  -> tier={r['tier']} tokens={r['tokens']} (skipped)")

    # (b) enabled + key present (Mock configured) -> brain runs -> tokens > 0
    mock = MockBrainClient()
    b = _agent(brain=mock, second_opinion=True)
    r = b.run_deal(strong, enrichment=_STRONG_ENRICHMENT)
    assert r["tier"] == CostTier.SHORTLIST.value
    assert r["tokens"] == 160 and mock.calls == 1, (r["tokens"], mock.calls)
    assert r["gate_trace"]["second_opinion"] is True
    assert r["advisory"].get("confidence") == 0.8
    print(f"  enabled + key     -> tier={r['tier']} tokens={r['tokens']} (Claude ran)")

    # (c) key present but DISABLED -> brain must NOT run
    mock2 = MockBrainClient()
    c = _agent(brain=mock2, second_opinion=False)
    r = c.run_deal(strong, enrichment=_STRONG_ENRICHMENT)
    assert r["tier"] == CostTier.SHORTLIST.value
    assert r["tokens"] == 0 and mock2.calls == 0, "disabled => no brain"
    print(f"  key + DISABLED    -> tier={r['tier']} tokens={r['tokens']} (skipped)")
    print("  [4] shortlist gating assertions passed.\n")


# ===========================================================================
# 5) TESTING MODE — open all gates, full treatment + training_observation
# ===========================================================================

def test_testing_mode_full_treatment():
    print("=" * 72)
    print("5) TESTING MODE — full treatment on a below-threshold deal")
    print("=" * 72)
    cfg = _cfg(testing={"open_all_gates": True})
    mock = MockBrainClient()
    agent = DealAnalyzerAgent(
        brain=mock,
        db_path=os.path.join(tempfile.mkdtemp(prefix="eva_test_"), "memory.db"),
        second_opinion=False, config=cfg,
    )
    assert agent.testing_mode is True

    # A LOG_ONLY-scoring deal (below 7.5): testing mode still gives full treatment.
    content = _mk("Content Site — Pet Care", "Content", 3000, 2.5)
    result = agent.run_deal(content)

    assert result["tier"] == CostTier.LOG_ONLY.value, "score stays below threshold"
    assert result["tokens"] > 0 and mock.calls == 1, "testing mode forces the brain"
    assert result["gate_trace"]["testing_mode"] is True

    obs = memory.list_training_observations(path=agent.db_path)
    assert len(obs) == 1, obs
    assert obs[0]["deal_id"] == result["deal"]["id"]
    assert obs[0]["tier"] == CostTier.LOG_ONLY.value
    assert float(obs[0]["v7_score"]) == result["deal"]["overall_score"]
    print(f"  {content.name}: tier={result['tier']} tokens={result['tokens']} "
          f"(full treatment despite low score)")
    print(f"  training_observation logged: id={obs[0]['id']} "
          f"v7_score={obs[0]['v7_score']} tier={obs[0]['tier']}")

    # closed-deal seam: a known_outcome flows into the training record.
    closed = _mk("Closed SaaS", "SaaS", 15000, 3.0, notes="already sold")
    ko = KnownOutcome(sale_price=540000, final_multiple=3.0, time_to_close_days=45)
    r2 = agent.run_deal(closed, known_outcome=ko)
    obs2 = memory.list_training_observations(path=agent.db_path)
    match = [o for o in obs2 if o["deal_id"] == r2["deal"]["id"]]
    assert match and "540000" in match[0]["known_outcome"], match
    print(f"  closed-deal known_outcome captured: {match[0]['known_outcome']}")
    print("  [5] testing-mode assertions passed.\n")


# ===========================================================================
# 6) RADAR DROP — logged, not scored
# ===========================================================================

def test_radar_drop_logged():
    print("=" * 72)
    print("6) RADAR DROP — unfit deal logged (tier=DROPPED), not scored")
    print("=" * 72)
    agent = _agent(brain=NoopClaudeClient(), second_opinion=False)
    unfit = _mk("Casino Affiliate", "Gambling", 12000, 3.0, notes="PBN network")
    result = agent.run_deal(unfit)

    assert result["dropped"] is True
    assert result["tier"] == "DROPPED"
    assert result["tokens"] == 0
    # dropped deals are NOT scored/saved to the deals table, but the run IS logged
    assert memory.get_deal(result["deal"]["id"], path=agent.db_path) is None
    runs = memory.list_runs(deal_id=result["deal"]["id"], path=agent.db_path)
    assert runs and "radar-drop" in runs[0]["notes"]
    print(f"  {unfit.name}: dropped={result['dropped']} "
          f"reasons={result['gate_trace']['radar_reasons']}")
    print("  [6] radar-drop assertions passed.\n")


def main() -> int:
    test_gate1_radar()
    test_route_and_second_opinion()
    test_log_only_no_brain()
    test_shortlist_second_opinion_gating()
    test_testing_mode_full_treatment()
    test_radar_drop_logged()
    print("=" * 72)
    print("ALL COST-GATE CASCADE ASSERTIONS PASSED  (fully offline)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
