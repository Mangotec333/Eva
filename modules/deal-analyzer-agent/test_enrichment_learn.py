"""
Offline self-test for the enrichment data layer + the learning loop.

PART 1 (enrichment): build an EnrichmentData, apply it to a sample deal, run
analyze_deal_v7 WITH and WITHOUT enrichment, and print both score sets so the
TAM / competitor deltas are visible. Also exercises NicheCache put/get.

PART 2 (learning): record 3 fake outcomes against scored deals in a temp DB, run
recalibrate() and print the proposed weight deltas, apply them, then print
get_learnings_summary().

No network, no LLM. Run:  python test_enrichment_learn.py
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone

import memory
from enrichment import (
    EnrichmentData, NicheCache, SourceRef, apply_enrichment, normalize_niche,
)
from learn import (
    apply_learning, get_learnings_summary, recalibrate, record_outcome,
)
from models import DealV7
from scoring_v7 import analyze_deal_v7


def _mk(name, category, monthly_net, annual_multiple, asking_price, age_years,
        decision="buy", notes=""):
    ts = datetime.now(timezone.utc).isoformat()
    return DealV7(
        id=str(uuid.uuid4()), source="manual", listing_id="", url="",
        name=name, category=category, monthly_net=monthly_net,
        annual_multiple=annual_multiple, asking_price=asking_price,
        age_years=age_years, buy_vs_build_decision=decision, notes=notes,
        discovered_at=ts, created_at=ts, updated_at=ts,
    )


def _fmt(deal):
    return (f"overall={deal.overall_score:<5} tam={deal.tam_score:<6} "
            f"competitor={deal.competitor_analysis_score:<6} "
            f"level={deal.research_level}")


def part1_enrichment():
    print("=" * 74)
    print("PART 1 — ENRICHMENT: apply contract to a deal, score with/without")
    print("=" * 74)

    enr = EnrichmentData(
        niche="b2b analytics saas",
        tam_usd=1_200_000_000, sam_usd=180_000_000,
        market_growth_rate_pct=18, tam_source_url="https://example.com/statista",
        tam_confidence_score=75,
        niche_growth_score=70, market_fragmentation_score=60,
        named_competitors=["CompetitorA", "CompetitorB", "CompetitorC"],
        estimated_market_share=12,
        research_level="L1", confidence_overall=72,
        source_urls=[
            SourceRef(url="https://example.com/statista", label="Statista TAM",
                      retrieved_at=datetime.now(timezone.utc).isoformat()).model_dump(),
            SourceRef(url="https://example.com/cbinsights", label="CB Insights competitors",
                      retrieved_at=datetime.now(timezone.utc).isoformat()).model_dump(),
        ],
        enriched_at=datetime.now(timezone.utc).isoformat(),
    )

    deal = _mk("Acme Analytics SaaS", "SaaS", monthly_net=12000,
               annual_multiple=4.2, asking_price=604800, age_years=6,
               notes="B2B analytics SaaS with API")

    kwargs = apply_enrichment(deal, enr)
    print(f"\napply_enrichment -> kwargs keys: {sorted(kwargs.keys())}")
    assert kwargs["tam_usd"] == 1_200_000_000
    assert kwargs["named_competitors"] == ["CompetitorA", "CompetitorB", "CompetitorC"]
    assert kwargs["estimated_market_share"] == 12

    bare = analyze_deal_v7(deal)
    enriched = analyze_deal_v7(deal, enrichment=kwargs)

    print("\n  WITHOUT enrichment : " + _fmt(bare))
    print("  WITH    enrichment : " + _fmt(enriched))
    print(f"\n  delta tam_score        : {bare.tam_score} -> {enriched.tam_score}")
    print(f"  delta competitor_score : {bare.competitor_analysis_score} -> "
          f"{enriched.competitor_analysis_score}")
    print(f"  delta research_level   : {bare.research_level} -> {enriched.research_level}")
    print(f"  delta overall_score    : {bare.overall_score} -> {enriched.overall_score}")

    assert bare.tam_score == 0.0, "no TAM -> tam_score 0"
    assert enriched.tam_score > 0.0, "TAM supplied -> tam_score > 0"
    assert bare.research_level == "L0"
    assert enriched.research_level == "L1", "named competitors + share -> L1"

    # NicheCache round-trip + TTL semantics.
    cache_path = os.path.join(tempfile.mkdtemp(), "enrichment_cache.db")
    cache = NicheCache(path=cache_path, ttl_days=14)
    assert cache.get("B2B Analytics SaaS") is None, "cold cache miss"
    cache.put("B2B Analytics SaaS", enr)
    hit = cache.get("b2b   analytics saas")            # normalization: different spacing/case
    assert hit is not None, "warm cache hit after put"
    assert hit.tam_usd == enr.tam_usd
    assert hit.niche == normalize_niche("B2B Analytics SaaS")
    print(f"\n  NicheCache: put+get OK (normalized key='{hit.niche}', "
          f"tam_usd={hit.tam_usd:,.0f}, cached research_level={hit.research_level})")

    # Expired entry (ttl=0) must miss.
    stale = NicheCache(path=cache_path, ttl_days=0)
    stale.put("stale niche", enr)
    assert stale.get("stale niche") is None, "ttl=0 -> immediate expiry"
    print("  NicheCache: TTL expiry OK (ttl_days=0 => miss)")

    print("\n  PART 1 assertions passed.")
    return deal, enr


def part2_learning():
    print("\n" + "=" * 74)
    print("PART 2 — LEARNING: record 3 outcomes, recalibrate, apply, summarize")
    print("=" * 74)

    tmp_db = os.path.join(tempfile.mkdtemp(), "memory.db")
    memory.init_db(tmp_db)

    # Two "winners" (high scores) and one "loser" (low score), scored + persisted.
    winner_enr = {
        "num_competitors": 3, "has_sdk_integration": True, "has_proprietary_data": True,
        "tam_usd": 1_500_000_000, "sam_usd": 200_000_000, "market_growth_rate_pct": 20,
        "tam_confidence_score": 80, "tam_source_url": "https://example.com/r",
        "niche_growth_score": 75, "market_fragmentation_score": 65,
        "named_competitors": ["A", "B"], "estimated_market_share": 15,
    }
    w1 = analyze_deal_v7(_mk("Winner SaaS One", "SaaS", 14000, 4.0, 672000, 7,
                             notes="SaaS API"), enrichment=winner_enr)
    w2 = analyze_deal_v7(_mk("Winner SaaS Two", "SaaS", 13000, 3.8, 592800, 6,
                             notes="SaaS API"), enrichment=winner_enr)
    loser = analyze_deal_v7(_mk("Loser FBA", "Digital Products", 4000, 2.8, 134400, 2,
                                notes="Amazon FBA inventory"),
                            enrichment={"peak_monthly_net": 12000, "owner_neglect_months": 8,
                                        "single_owner_dependent": True})

    for d in (w1, w2, loser):
        memory.save_deal(d.model_dump(), path=tmp_db)
    print(f"\n  scored+persisted: {w1.name}={w1.overall_score}, "
          f"{w2.name}={w2.overall_score}, {loser.name}={loser.overall_score}")

    record_outcome(w1.id, stage="loi_sent", outcome="LOI",
                   notes="Strong TAM + moat; owner cooperative.", db_path=tmp_db)
    record_outcome(w2.id, stage="closed", outcome="closed",
                   notes="Closed at 3.8x; SDK lock-in held.", db_path=tmp_db)
    record_outcome(loser.id, stage="in_progress", outcome="passed_on",
                   notes="Thin market, heavy platform + neglect risk.", db_path=tmp_db)
    print("  recorded 3 outcomes: LOI, closed, passed_on")

    proposal = recalibrate(db_path=tmp_db)
    print(f"\n  recalibrate(): {proposal['n_positive']} positive / "
          f"{proposal['n_negative']} negative learnings; "
          f"logged as {proposal.get('logged_version')}")
    print("  proposed weight deltas (positive => winners scored higher on this axis):")
    for axis, rep in sorted(proposal["dimension_report"].items(),
                            key=lambda kv: kv[1]["separation"], reverse=True):
        print(f"    {axis:<26} sep={rep['separation']:>7} "
              f"delta={rep['proposed_weight_delta']:+.5f} "
              f"({rep['current_weight']:.3f} -> {rep['proposed_weight']:.5f})")

    assert proposal["n_positive"] == 2 and proposal["n_negative"] == 1
    assert proposal["proposed_deltas"], "expected non-empty proposed deltas"

    # Non-destructive: base weights untouched. Apply into an isolated override file.
    from scoring_v7 import V7_WEIGHTS
    override_path = os.path.join(tempfile.mkdtemp(), "learned_weights.json")
    applied = apply_learning(proposal["proposed_deltas"],
                             weights_path=override_path, db_path=tmp_db)
    assert V7_WEIGHTS["tam"] == 0.09, "base V7_WEIGHTS must be unchanged (non-destructive)"
    print(f"\n  apply_learning(): wrote override -> {os.path.basename(override_path)}")
    print(f"    e.g. tam weight {V7_WEIGHTS['tam']} (base) -> {applied['tam']} (learned)")

    # Re-score a deal with the learned override to prove the plumbing works.
    rescored = analyze_deal_v7(_mk("Winner SaaS One", "SaaS", 14000, 4.0, 672000, 7,
                                   notes="SaaS API"),
                               enrichment=winner_enr, weights_override=applied)
    print(f"    re-scored winner with learned weights: {w1.overall_score} -> "
          f"{rescored.overall_score}")

    summary = get_learnings_summary(db_path=tmp_db)
    print("\n  get_learnings_summary():")
    print(f"    n_deals={summary['n_deals']} outcomes={summary['outcome_counts']}")
    print(f"    mean_score_positive={summary['mean_score_positive']} "
          f"mean_score_negative={summary['mean_score_negative']}")
    print(f"    high_score(>= {summary['high_score_threshold']}) precision="
          f"{summary['high_score_precision']} over n={summary['high_score_n']}")
    print("    top lessons:")
    for l in summary["top_lessons"]:
        print(f"      [{l['outcome']}] {l['lesson']}")

    assert summary["outcome_counts"].get("LOI") == 1
    assert summary["mean_score_positive"] > (summary["mean_score_negative"] or 0)
    print("\n  PART 2 assertions passed.")


def main():
    part1_enrichment()
    part2_learning()
    print("\n\nALL ENRICHMENT + LEARNING ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    main()
