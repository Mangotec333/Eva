"""
Offline self-test for the v7 scoring core.

Constructs three sample deals (SaaS, Physical Ecommerce, Services), runs
analyze_deal_v7() with and without enrichment, and prints all scores. No network,
no LLM — this is the proof that the engine is fully deterministic and testable in
isolation.

Run:  python test_v7.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from models import DealV7
from scoring_v7 import analyze_deal_v7, V7_WEIGHTS, migrate_category


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


def _print(deal: DealV7, label: str):
    print(f"\n{'='*74}\n{label}\n{'='*74}")
    print(f"  name                 : {deal.name}")
    print(f"  category (legacy)    : {deal.category}")
    print(f"  category_v2          : {deal.category_v2}")
    print(f"  research_level       : {deal.research_level}")
    print(f"  scoring_version      : {deal.scoring_version}")
    print("  --- v7 dimensions (0-100 unless noted) ---")
    print(f"  cashflow_score       : {deal.cashflow_score}")
    print(f"  profit_potential     : {deal.profit_potential_score}")
    print(f"  exit_potential       : {deal.exit_potential_score}")
    print(f"  moat_score           : {deal.moat_score}")
    print(f"  tam_score            : {deal.tam_score}")
    print(f"  competitor_analysis  : {deal.competitor_analysis_score}")
    print(f"  ai_proof_score       : {deal.ai_proof_score}")
    print(f"  company_life_score    : {deal.company_life_score} ({deal.company_life_label}, {deal.company_life_months}mo)")
    print(f"  buy_vs_build_score   : {deal.buy_vs_build_score} (0-10)")
    print(f"  mitigation_score     : {deal.mitigation_score}")
    print(f"  owner_neglect_score  : {deal.owner_neglect_score}")
    print(f"  platform_dep_risk    : {deal.platform_dependency_risk_score}")
    print(f"  risk_score           : {deal.risk_score}")
    print(f"  >> OVERALL_SCORE     : {deal.overall_score} / 10")
    print("  --- financial ---")
    print(f"  down_payment         : ${deal.down_payment:,.0f}")
    print(f"  monthly_debt_service : ${deal.monthly_debt_service:,.0f}")
    print(f"  net_after_heloc      : ${deal.net_after_heloc:,.0f}/mo")
    print(f"  breakeven_w_draw     : {deal.breakeven_months_with_draw} months")
    top = sorted(deal.profit_lever_scores.items(),
                 key=lambda kv: kv[1]["lever_score"], reverse=True)[:3]
    print("  --- top profit levers ---")
    for lever, d in top:
        print(f"    {lever:<24}: {d['lever_score']} (up={d['addable_upside']}, "
              f"util={d['current_utilization']}, feas={d['feasibility']}, ev={d['evidence_confidence']})")


def main():
    print("V7 composite weights (sum = %.4f):" % sum(V7_WEIGHTS.values()))
    for k, v in V7_WEIGHTS.items():
        print(f"  {k:<26}: {v:.2f}")

    # Taxonomy-mapper spot checks
    print("\nmigrate_category spot checks:")
    for legacy, hint in [
        ("SaaS", ""), ("Services", ""), ("Digital Products", "Amazon FBA store"),
        ("Digital Products", "Lightroom plugin app"), ("Digital Products", ""),
        ("Content", ""), ("Education", ""),
    ]:
        print(f"  {legacy!r:<20} + {hint!r:<28} -> {migrate_category(legacy, hint)!r}")

    # --- Sample 1: SaaS, healthy, fully enriched --------------------------
    saas = _mk("Acme Analytics SaaS", "SaaS", monthly_net=12000,
               annual_multiple=4.2, asking_price=604800, age_years=6,
               notes="B2B analytics SaaS with API")
    saas_enr = {
        "num_competitors": 4,
        "has_sdk_integration": True,
        "has_proprietary_data": True,
        "tam_usd": 1_200_000_000, "sam_usd": 180_000_000,
        "market_growth_rate_pct": 18, "tam_confidence_score": 75,
        "tam_source_url": "https://example.com/market-report",
        "niche_growth_score": 70, "market_fragmentation_score": 60,
        "named_competitors": ["CompetitorA", "CompetitorB"],
        "estimated_market_share": 12,
        "platform_name": "AWS Marketplace", "platform_native_overlap_pct": 0.1,
    }
    _print(analyze_deal_v7(saas, enrichment=saas_enr), "SAMPLE 1 — SaaS (fully enriched)")

    # --- Sample 2: Physical Ecommerce, declining, NO enrichment -----------
    ecom = _mk("Trendy Gadgets FBA", "Digital Products", monthly_net=9000,
               annual_multiple=2.6, asking_price=280800, age_years=3,
               notes="Amazon FBA inventory ecommerce brand")
    ecom_enr = {"peak_monthly_net": 15000, "owner_neglect_months": 6,
                "single_owner_dependent": True, "platform_name": "Amazon"}
    _print(analyze_deal_v7(ecom, enrichment=ecom_enr),
           "SAMPLE 2 — Physical Ecommerce (declining, minimal enrichment / no TAM)")

    # --- Sample 3: Services, backward-compatible (no enrichment at all) ----
    svc = _mk("Managed IT Services Co", "Services", monthly_net=11000,
              annual_multiple=3.1, asking_price=409200, age_years=8)
    _print(analyze_deal_v7(svc), "SAMPLE 3 — Services (backward-compatible: zero enrichment)")

    # --- assertions -------------------------------------------------------
    assert abs(sum(V7_WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"
    s = analyze_deal_v7(saas, enrichment=saas_enr)
    e = analyze_deal_v7(ecom, enrichment=ecom_enr)
    v = analyze_deal_v7(svc)
    assert s.category_v2 == "SaaS"
    assert e.category_v2 == "Physical Ecommerce"
    assert v.category_v2 == "Services"
    assert e.tam_score == 0.0, "no TAM supplied -> tam_score must be 0 (graceful)"
    assert s.tam_score > 0.0, "TAM supplied -> tam_score must be > 0"
    assert s.research_level == "L1", "named competitors + share -> L1"
    assert v.research_level == "L0", "no competitor research -> L0"
    assert all(0 <= d.overall_score <= 10 for d in (s, e, v))
    assert len(s.profit_lever_scores) == 12, "12 growth levers expected"
    print("\n\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    main()
