"""One-off intel ingest: Acquire.com listing 97MLWWoUHSPPFjqsZv88RemyCrM2.

Scores the deal through the v6 11-param composite, stores raw deal + score,
attaches competitor intel (HackerRank, Roadmap.sh + adjacent vetted-talent
marketplaces), and records a 4-lens case study. Run once against the live
deal-scout DB to persist this intelligence in EVA.

The generic normalize → score → persist work is delegated to
``acquire_ingest.ingest_listing``; only this listing's hand-researched intel
lives here.  New Acquire.com listings should use ``cli.py ingest-acquire``
rather than a copy of this script.

Usage: python scripts/ingest_acquire_97MLWWoU.py [path/to/eva-deal-scout.db]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acquire_ingest import ingest_listing
from store import SQLiteDealStore

URL = "https://app.acquire.com/startup/97MLWWoUHSPPFjqsZv88RemyCrM2/eF646qqNwAsFhwXoOwtr"
LISTING_ID = "97MLWWoUHSPPFjqsZv88RemyCrM2"

COMPETITORS = [
    dict(
        name="HackerRank",
        what_they_do="Enterprise technical-assessment & interview SaaS (coding "
        "tests, AI proctoring, ATS integrations) for high-volume corporate hiring.",
        pricing_model="Seat-based SaaS subscription: Starter $165-199/mo (1 user, "
        "120 attempts/yr), Pro $375-449/mo (unlimited users, 300 attempts/yr), "
        "Enterprise custom (up to 100k candidates, 40+ integrations).",
        url="https://www.hackerrank.com/pricing",
        moat_comparison="Much larger scale/brand (7,500+ question library, "
        "venture-funded) but different buyer (enterprise recruiting teams, not "
        "individual engineers) -- only adjacent, not a direct head-to-head competitor.",
        source_url="https://www.hackerrank.com/pricing",
        category="SaaS",
    ),
    dict(
        name="Roadmap.sh",
        what_they_do="Free, community-curated developer career/skill roadmaps and "
        "learning guides (open-source project, kamranahmedse/developer-roadmap).",
        pricing_model="Free to use; monetized via sponsorships/ads, not a paid "
        "product -- no direct subscription revenue model.",
        url="https://roadmap.sh/",
        moat_comparison="No moat overlap: free community content vs. a paid "
        "vetting/assessment product -- weak comp, mainly shares an SEO/discovery "
        "audience (developers exploring career paths).",
        source_url="https://roadmap.sh/",
        category="Content",
    ),
    dict(
        name="Toptal",
        what_they_do="Premium vetted freelance marketplace for top ~3% engineers.",
        pricing_model="Hourly $80-$200/hr, $500 upfront deposit, no subscription.",
        url="https://www.toptal.com/",
        moat_comparison="Established brand + rigorous vetting funnel; direct "
        "competitor in the 'vetted engineering talent' category the target "
        "business is adjacent to.",
        source_url="https://www.index.dev/blog/toptal-turing-arcdev-bairesdev-indexdev-comparison",
        category="Services",
    ),
    dict(
        name="Turing",
        what_they_do="AI-matched vetted remote developer marketplace, pivoting "
        "toward AI-eval/domain-expert engagements in 2026.",
        pricing_model="$60-$200/hr project rates, no upfront cost, 2-week trial.",
        url="https://www.turing.com/",
        moat_comparison="AI-driven matching at scale; bigger balance sheet, "
        "direct competitor for vetted-talent positioning.",
        source_url="https://www.index.dev/blog/toptal-turing-arcdev-bairesdev-indexdev-comparison",
        category="Services",
    ),
    dict(
        name="Arc.dev",
        what_they_do="Global remote-talent marketplace with AI matching, ~450k "
        "pre-screened professionals across 190+ countries.",
        pricing_model="$15-$110+/hr freelance; % fee for full-time placements.",
        url="https://arc.dev/",
        moat_comparison="Much larger network/scale; direct competitor with a "
        "lower price point than Toptal/Turing.",
        source_url="https://www.secondtalent.com/alternatives/toptal/",
        category="Services",
    ),
    dict(
        name="Index.dev",
        what_they_do="Senior-only vetted contractor marketplace, sub-3% "
        "acceptance rate, 27,000+ engineers.",
        pricing_model="Monthly contract rates $60-$90/hr equivalent, 30-day "
        "risk-free trial, no upfront cost.",
        url="https://www.index.dev/",
        moat_comparison="Best value-to-quality positioning per third-party "
        "comparisons; direct competitor.",
        source_url="https://www.index.dev/blog/top-turing-alternatives",
        category="Services",
    ),
]


LISTING = {
    "url": URL,
    "listing_id": LISTING_ID,
    "name": "UK SaaS -- Career Dev / Talent Vetting for Engineers (Acquire.com)",
    "category": "SaaS",
    "monthly_net": 1450.0,          # TTM avg profit ($17.4k / 12)
    "annual_multiple": 11.8,        # per listing (profit multiple)
    "asking_price": 204600.0,
    "age_years": 2.83,              # founded Sept 2023
    "currency": "USD",
    "registration_country": "GB",
    "primary_customer_market": "",  # not disclosed
    "seller_location": "United Kingdom",
    "market_status": "available",
    # Digital-micro box inputs, carried through to raw_json.
    "ttm_revenue": 122300.0,
    "ttm_profit": 17400.0,
    "ttm_avg_net": 1450.0,
    "last_month_revenue": 14400.0,
    "last_month_net": 371.0,
    "monthly_churn": 0.075,         # seller reports 5-10%
    "age_months": 34.0,
    "notes": (
        "UK-based bootstrapped SaaS, career development/talent-vetting for "
        "engineers. TTM revenue $122.3k, TTM profit $17.4k, last-month "
        "revenue $14.4k / profit $371. <10 customers, churn 5-10% ('stable' "
        "per seller). Annual growth -5%. Team 2-20, services/agency revenue "
        "model. Stack: Netlify/MongoDB/Vercel/OpenAI/Express/Node/GCP/"
        "React Native/React. 97 buyers viewed as of ingest date. Seller "
        "cites 'business challenges' and 'lack of time' as reasons for sale."
    ),
}

ANALYZER_KWARGS = dict(
    num_competitors=len(COMPETITORS),
    has_sdk_integration=False,
    has_proprietary_data=False,
    has_network_effect=False,
    single_owner_dependent=True,
    revenue_declining=True,
    peak_monthly_net=1450.0,
    financing_required=True,
    revenue_floor=500.0,
)


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "eva-deal-scout.db"
    store = SQLiteDealStore(db_path)
    store.migrate()

    # Everything generic (normalize -> gate -> score -> persist) is the shared
    # Acquire.com ingest path; only this listing's researched intel is local.
    result = ingest_listing(
        store, LISTING, competitors=COMPETITORS, analyzer_kwargs=ANALYZER_KWARGS)

    raw_deal_id = result["raw_deal_id"]
    scoring = result["scoring"]
    gate_reason = scoring["reason"]
    scores = scoring["scores"]

    store.add_case_study(
        source_url=URL,
        deal_type="within_box",
        title="Acquire.com: UK SaaS career-dev/talent-vetting listing (2026-07)",
        deal_id=raw_deal_id,
        snapshot={
            "asking_price": 204600,
            "ttm_revenue": 122300,
            "ttm_profit": 17400,
            "last_month_revenue": 14400,
            "last_month_profit": 371,
            "annual_growth": "-5%",
            "customers": "<10",
            "churn": "5-10%",
            "multiple_profit": 11.8,
            "multiple_revenue": 1.7,
            "founded": "2023-09",
            "team_size": "2-20",
            "location": "United Kingdom",
            "usp": "Career development / talent-vetting platform for engineers",
        },
        analysis={
            "lens1_box_fit": gate_reason + (
                " -- would sit un-scored in raw_deals under the automated "
                "pipeline unless a box disables the gate or Acquire.com is "
                "manually elevated to trust_level=high. This score was "
                "force-scored past the gate by the Acquire.com ingest path."
            ),
            "lens2_what_selling": (
                "A sub-$20k profit/yr, <10-customer, declining-revenue "
                "bootstrapped SaaS asking 11.8x profit / 1.7x revenue. "
                f"Overall composite {scores['overall_score']}/10 -- cashflow "
                f"score high ({scores['cashflow_score']}/100) only because "
                "monthly net is tiny relative to scoring scale; real risk "
                f"({scores['risk_score']}/100), weak moat "
                f"({scores['moat_score']}/100), and weak competitive position "
                f"({scores['competitor_analysis_score']}/100) drag the deal down."
            ),
            "lens3_juggernaut_arc": (
                "Not a juggernaut pattern: revenue declining -5% YoY, "
                "<10 customers 2.8 years post-founding, services/agency "
                "model bolted onto a SaaS shell -- looks like a founder-time "
                "constrained side project, not a compounding business."
            ),
            "lens4_build_vs_buy": (
                f"buy_vs_build_score {scores['buy_vs_build_score']}/10 leans "
                "toward buying the shell (stack, OpenAI integration, some "
                "brand/domain equity) over building from scratch, but the "
                "crowded, well-funded vetted-talent-marketplace competitive "
                "set (Toptal/Turing/Arc.dev/Index.dev) makes the standalone "
                "acquisition thesis weak without a clear distribution edge."
            ),
        },
        pattern_tags=[
            "gate_skipped_geography", "declining_revenue", "thin_customer_base",
            "crowded_vetted_talent_category", "uk_seller",
        ],
        formula_insight=(
            "HackerRank and Roadmap.sh (the two competitors named in the "
            "original teaser) are weak comps -- HackerRank sells enterprise "
            "assessment SaaS to recruiters, Roadmap.sh is a free community "
            "resource. The real competitive set for a talent-vetting/career-"
            "dev product is the vetted-freelance-marketplace category "
            "(Toptal, Turing, Arc.dev, Index.dev), which is well-capitalized "
            "and would out-compete a 2-person, <10-customer bootstrapped shop "
            "on trust, scale, and CAC."
        ),
    )

    print(f"raw_deal_id={raw_deal_id} is_new={result['is_new']}")
    print(f"gate: {gate_reason} (forced={scoring['forced']})")
    print(
        f"overall_score={scores['overall_score']} risk={scores['risk_score']} "
        f"moat={scores['moat_score']} "
        f"competitor={scores['competitor_analysis_score']}"
    )


if __name__ == "__main__":
    main()
