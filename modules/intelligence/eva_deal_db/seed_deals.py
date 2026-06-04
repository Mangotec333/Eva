"""
Eva Deal Intelligence — Seed Script
Populates eva_deals.db with all known deals as of June 2026.

Run: python seed_deals.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from deal_repository import DealRepository, Deal
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/Eva/data/eva_deals.db")
repo = DealRepository(db_path=DB_PATH)

now = datetime.now(timezone.utc).isoformat()

# ============================================================
# DEAL 1: batch.ai — PRIMARY ACTIVE DEAL
# Empire Flippers #87872
# Swoop financing: $179K purchase, 10% down, 10% rate, 10yr
# ============================================================
batch_ai = Deal(
    id              = "batch-ai",
    name            = "batch.ai",
    alias           = "Batch AI, batch ai, #87872",
    platform        = "Empire Flippers",
    asset_type      = "saas",
    market          = "Photography / Adobe Lightroom ecosystem",
    tier            = 1,
    status          = "loi-sent",

    asking_price    = 179_000,
    purchase_price  = 179_000,
    multiple        = 3.47,            # 179K / (52K annualised from peak) — conservative
    down_payment    = 17_900,
    loan_amount     = 161_100,
    loan_rate       = 0.10,
    loan_term_yrs   = 10,
    loan_payment_mo = 2_129,

    # Financials at current MRR (Apr 2026)
    gross_revenue_mo  = 4_299,          # Apr 2026 actual MRR
    operating_exp_mo  = 799,
    ebitda_mo         = 3_500,
    total_debt_mo     = 2_129,
    noi_mo            = 1_371,
    noi_annual        = 16_452,

    # Peak MRR reference
    mrr               = 4_299,          # current
    mrr_peak          = 15_611,         # Nov 2024 peak
    noi_peak_mo       = 12_683,         # NOI at peak MRR after debt service

    risk_score = 7.2,
    risk_flags = [
        "Adobe LR SDK dependency — 4 scenarios: Lua SDK (low risk), Creative SDK deprecated (high), developer ID transfer (medium), pricing change (moderate)",
        "MRR declined 72% from peak $15,611 (Nov 2024) to $4,299 (Apr 2026)",
        "Single-product SaaS — no revenue diversification",
        "Holdback condition: Day 60 MRR must be >= 100% of LOI MRR (strict)"
    ],

    # Timeline
    loi_date          = "2026-06-01",
    dd_days           = 10,
    exclusivity_days  = 7,
    holdback_pct      = 0.30,          # 30% = $53,700 held
    holdback_days     = 60,
    transition_days   = 60,
    transition_hrs_wk = 5.0,           # LOI PDF says 5hrs/wk

    # Contacts
    seller_name       = "Shawn Hawkins",
    seller_email      = "support@batch.ai",
    broker_platform   = "Empire Flippers",

    # Eva
    eva_score    = 62.0,               # good deal certainty, risky MRR trend
    eva_notes    = (
        "LOI signed June 1 2026. Gmail draft ready to send to support@batch.ai. "
        "Broker call Wednesday — confirm lien structure + closing costs. "
        "Bolt-on: Gabriela sales ops at $2K/mo post-close. "
        "Payment structure: 70% at close ($125,300) + 30% holdback Day 60 ($53,700). "
        "Swoop financing confirmed: $161,100 @ 10%, 10yr, no collateral. "
        "Key DD items: Stripe data, MRR CSV, churn, GitHub access, Adobe SDK docs."
    ),
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_url    = "https://app.empireflippers.com/listing/87872",
    source_doc_id = "1Cj83kzHbWT7OvU0GdJK1-i-NfHaNMXEO",  # Drive term sheet
    extra_fields  = {
        "ef_listing_id": "87872",
        "payment_at_close": 125_300,
        "payment_holdback": 53_700,
        "dd_items": ["Stripe", "MRR CSV", "churn data", "GitHub", "Adobe LR SDK docs"],
        "broker_call_date": "2026-06-03",
        "pl_sheet_id": "1ig9I1t_9XDdqQRGSORFYMcFw2omJRv59ah2I5s-Q3Vk",
        "adobe_sdk_scenarios": {
            "lua_sdk": "low risk — standard transferable",
            "creative_sdk": "high risk — deprecated by Adobe",
            "developer_id": "medium risk — transfer may require Adobe approval",
            "pricing_change": "moderate — Adobe could raise SDK costs"
        }
    }
)

# ============================================================
# DEAL 2: Mission Villa / SSS — RCFE ACTIVE ASSET
# Existing asset being acquired via HELOC financing
# ============================================================
mission_villa = Deal(
    id           = "mission-villa",
    name         = "Mission Villa (SSS)",
    alias        = "SSS, Yealem LLC, Mission Villa RCFE, mission villas",
    platform     = "Direct / Storeys",
    asset_type   = "rcfe",
    market       = "Southern California",
    tier         = 1,
    status       = "in-dd",

    asking_price = 2_260_000,
    purchase_price = 2_260_000,
    multiple     = None,                # N/A for RCFE — use cap rate
    cap_rate     = 0.0379,              # NOI $85,536 / $2.26M ≈ 3.79% (net of all debt)

    # HELOC financing structure
    loan_amount     = 460_000,          # $260K + $200K HELOC
    loan_rate       = None,             # blended: see below
    loan_payment_mo = 3_975,            # HELOC total: $2,058 + $1,917

    # Actuals from Yealem LLC P&L 2025 (Jan–Nov)
    gross_revenue_mo  = 52_900,
    operating_exp_mo  = 31_075,
    ebitda_mo         = 21_825,
    total_debt_mo     = 14_697,         # existing mortgage $10,722 + HELOC $3,975
    noi_mo            = 7_128,
    noi_annual        = 85_536,

    risk_score = 3.5,
    risk_flags = [
        "Existing mortgage $10,722/mo must be serviced regardless",
        "HELOC interest-only periods may reset — confirm terms",
        "RCFE licensing dependency — California CDSS regulations",
        "Payroll is 60%+ of operating costs — staffing risk"
    ],

    # Contacts
    broker_name = "Vineetkumar Ravi (Storeys LLC)",

    # Eva
    eva_score   = 81.0,
    eva_notes   = (
        "Actual 2025 data from Yealem LLC P&L (Drive SBA Loan folder). "
        "Gross revenue $52,900/mo, opex $31,075/mo, EBITDA $21,825/mo. "
        "Debt structure: existing mortgage $10,722/mo + HELOC $260K@9.5% ($2,058) + HELOC $200K@11.5% ($1,917) = $14,697/mo total. "
        "Net NOI $7,128/mo = $85,536/yr. "
        "Financial projections (Drive v1.1): 2026 $25,039/mo net, 2027 $28,517/mo net. "
        "2024 actuals: revenue $626,600, expenses $407,431, net $219,169."
    ),
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_doc_id   = "1KmaFwaBf9_1ch6NnmH79CZxIBXC266qY",   # Financial projections v1.1
    extra_fields = {
        "yealem_pl_2025_id": "1TcDEApQZ6YxEyiIYIIWwWvoI_b9qfFrXQ",
        "pl_2024_id": "17Fo-TCwgsJv3vDX6DxDrbKph8AxQ75r6",
        "heloc_1": {"amount": 260_000, "rate": 0.095, "monthly": 2_058},
        "heloc_2": {"amount": 200_000, "rate": 0.115, "monthly": 1_917},
        "existing_mortgage_mo": 10_722,
        "payroll_mo_avg": 17_750,
        "license_type": "RCFE — California CDSS",
        "noi_2026_projected_mo": 25_039,
        "noi_2027_projected_mo": 28_517,
    }
)

# ============================================================
# DEAL 3: HTML Framework SaaS — TIER 1 FALLBACK
# Flippa — best alternative if batch.ai falls through
# ============================================================
html_framework = Deal(
    id           = "html-framework-saas",
    name         = "HTML Framework SaaS",
    alias        = "HTML framework, Flippa 11983445",
    platform     = "Flippa",
    asset_type   = "saas",
    market       = "Web Development Tools",
    tier         = 1,
    status       = "watch",

    asking_price    = 157_950,
    multiple        = 2.75,            # $157,950 / $57,432 annual profit
    gross_revenue_mo  = 4_786,
    operating_exp_mo  = 0,             # 100% margins reported
    ebitda_mo         = 4_786,
    noi_mo            = 4_786,         # pre-debt service
    noi_annual        = 57_432,

    risk_score = 4.2,
    risk_flags = [
        "100% margin claim requires verification — check hosting/CDN costs",
        "75K users with no mention of paid conversion rate",
        "13yr old product — may be legacy tech stack"
    ],

    eva_score  = 74.0,
    eva_notes  = (
        "Best fallback if batch.ai LOI rejected. "
        "100% margins and 13yr history are strong signals. "
        "75K users is a moat. Lower multiple than batch.ai. "
        "No churn data visible — critical DD item."
    ),
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_url  = "https://flippa.com/11983445",
)

# ============================================================
# DEAL 4: B2B HR Data Platform — TIER 1 WATCH
# Acquire.com — 700K HR leaders database
# ============================================================
b2b_hr_data = Deal(
    id           = "b2b-hr-data-platform",
    name         = "B2B HR Data Platform",
    alias        = "HR data, HR contact database, Acquire.com hr",
    platform     = "Acquire.com",
    asset_type   = "hr-data",
    market       = "HR / Talent Intelligence",
    tier         = 1,
    status       = "watch",

    asking_price    = 120_000,
    gross_revenue_mo  = 6_000,          # TTM average
    noi_mo            = 6_000,          # assumption — verify opex
    noi_annual        = 72_000,
    multiple          = 1.67,

    risk_score = 5.8,
    risk_flags = [
        "Data freshness unknown — 700K contacts could be stale",
        "GDPR/CCPA compliance risk for contact data resale",
        "No moat beyond database size — easily replicated"
    ],

    eva_score  = 61.0,
    eva_notes  = (
        "700K HR leader contacts in North America. $120K ask, ~$6K TTM. "
        "Low multiple (1.67x) is attractive but data freshness is the existential question. "
        "Regulatory risk: selling contact data post-GDPR requires clear consent chain."
    ),
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_url  = "https://app.acquire.com/startup/7mj9x4yr4l-b2b-contact-data-platform-in-the-hr-talent-niche-database-of-700k-hr-leaders-in-north-america",
)

# ============================================================
# DEAL 5: AI Dropshipping SaaS — TIER 1 WATCH
# Flippa — strong margins, some churn
# ============================================================
ai_dropshipping = Deal(
    id           = "ai-dropshipping-saas",
    name         = "AI Dropshipping SaaS",
    alias        = "dropshipping saas, Flippa 12657501",
    platform     = "Flippa",
    asset_type   = "saas",
    market       = "E-Commerce / Dropshipping",
    tier         = 1,
    status       = "watch",

    asking_price    = 95_000,
    gross_revenue_mo  = 4_280,
    operating_exp_mo  = 600,            # 86% margin implies ~$600 opex
    ebitda_mo         = 3_680,
    noi_mo            = 3_680,
    noi_annual        = 44_160,
    multiple          = 2.15,

    risk_score = 5.5,
    risk_flags = [
        "15% monthly churn — customers cycling in/out",
        "Dropshipping niche is highly competitive",
        "AI claim requires validation — may be basic automation"
    ],

    eva_score  = 67.0,
    eva_notes  = (
        "86% margins are excellent for SaaS. $95K asking with $4,280 MRR. "
        "15% monthly churn is the key concern — net retention could be negative. "
        "Synergy with Vineet's existing Pureplate/dropship operation."
    ),
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_url  = "https://flippa.com/12657501",
)

# ============================================================
# DEAL 6: Business SaaS 0% Churn — TIER 2 WATCH
# Flippa — tiny deal, 0% churn claim interesting
# ============================================================
business_saas_zero_churn = Deal(
    id           = "business-saas-zero-churn",
    name         = "Business SaaS 0% Churn",
    alias        = "zero churn saas, Flippa 12813164",
    platform     = "Flippa",
    asset_type   = "saas",
    market       = "Business SaaS",
    tier         = 2,
    status       = "watch",

    asking_price    = 40_000,
    gross_revenue_mo  = 2_696,
    noi_mo            = 2_696,
    noi_annual        = 32_352,
    multiple          = 1.20,

    risk_score = 5.0,
    risk_flags = [
        "0% churn claim needs verification — likely small customer base",
        "Very low multiple (1.2x) could signal hidden problems",
        "Low revenue — insufficient to move financial needle alone"
    ],

    eva_score  = 58.0,
    eva_notes  = "Interesting 0% churn claim but $2,696 MRR is too small to be primary deal. Could be bolt-on.",
    watchlist_added = "2026-06-01T00:00:00+00:00",
    source_url  = "https://flippa.com/12813164",
)

# ============================================================
# TIER 3: QUIETLIGHT RADAR DEALS
# ============================================================
ql_design_education = Deal(
    id           = "ql-design-education",
    name         = "Design Education (Quietlight)",
    alias        = "quietlight design, design education seller financed",
    platform     = "Quietlight",
    asset_type   = "content-site",
    market       = "Design Education",
    tier         = 3,
    status       = "watch",
    asking_price = 145_000,
    multiple     = 3.17,
    risk_score   = 5.5,
    risk_flags   = ["Seller financing available — good signal of confidence"],
    eva_notes    = "Seller-financed at $145K, 3.17x multiple. Education niche has durable demand.",
    watchlist_added = now,
    source_url   = "https://quietlight.com",
)

ql_food_content = Deal(
    id           = "ql-food-content-site",
    name         = "Food Content Site (Quietlight)",
    alias        = "food content, yahoo moat quietlight",
    platform     = "Quietlight",
    asset_type   = "content-site",
    market       = "Food / Recipes",
    tier         = 3,
    status       = "watch",
    asking_price = 199_000,
    multiple     = 2.26,
    risk_score   = 5.0,
    risk_flags   = ["Yahoo distribution moat — single-platform dependency risk"],
    eva_notes    = "$199K, 2.26x. Yahoo moat noted — validate traffic source diversification.",
    watchlist_added = now,
    source_url   = "https://quietlight.com",
)

ql_amazon_fba = Deal(
    id           = "ql-amazon-fba",
    name         = "Amazon FBA (Quietlight)",
    alias        = "amazon fba quietlight",
    platform     = "Quietlight",
    asset_type   = "ecomm",
    market       = "Amazon / E-Commerce",
    tier         = 3,
    status       = "watch",
    asking_price = 140_000,
    multiple     = 1.49,
    risk_score   = 6.5,
    risk_flags   = ["Amazon platform dependency — account suspension risk", "Low multiple may signal operational complexity"],
    eva_notes    = "$140K, 1.49x. Low multiple but Amazon risk is real. Deprioritized.",
    watchlist_added = now,
    source_url   = "https://quietlight.com",
)

ql_womens_health = Deal(
    id           = "ql-womens-health",
    name         = "Women's Health Site (Quietlight)",
    alias        = "womens health quietlight",
    platform     = "Quietlight",
    asset_type   = "content-site",
    market       = "Women's Health",
    tier         = 3,
    status       = "watch",
    asking_price = 149_000,
    multiple     = 2.50,
    risk_score   = 5.5,
    risk_flags   = ["Google HCU volatility for health content", "YMYL niche requires credentialed content"],
    eva_notes    = "$149K, 2.5x. Health niche = Google algorithm risk. Deprioritized vs batch.ai.",
    watchlist_added = now,
    source_url   = "https://quietlight.com",
)

# ============================================================
# SEED ALL DEALS
# ============================================================
all_deals = [
    batch_ai,
    mission_villa,
    html_framework,
    b2b_hr_data,
    ai_dropshipping,
    business_saas_zero_churn,
    ql_design_education,
    ql_food_content,
    ql_amazon_fba,
    ql_womens_health,
]

print(f"Seeding {len(all_deals)} deals into {DB_PATH}...")

for deal in all_deals:
    repo.upsert(deal, embed=False)   # embed=False until embedder is configured
    # Log initial creation event
    repo.log_event(deal.id, "created", note=f"Initial seed from Eva session June 2026")
    print(f"  ✓ {deal.name} [{deal.tier}] [{deal.status}]")

# Verify
stats = repo.stats()
print(f"\nDone. DB stats: {stats}")

repo.close()
