"""
EVA Deal Scout — Scoring & Financial Analysis Engine (v6)
=========================================================

Implements analyze_deal(deal: Deal) -> Deal, computing:
  - cashflow_score              (0–100)
  - moat_score                  (0–100)  defensibility depth
  - ai_proof_score              (0–100)  [can be pre-set by user]
  - value_add_score             (0–100)  [manual / preserved if already set]
  - buy_vs_build_score          (0–10)   [derived from buy_vs_build_decision unless manually set]
  - risk_score                  (0–100)
  - competitor_analysis_score   (0–100)  market crowding & competitive intensity
  - company_life_score          (0–100)  survival runway if owner does nothing
  - mitigation_score            (0–100)  how well risks can be offset
  - owner_neglect_score         (0–100)  damage from operator absence (v6 NEW)
  - adobe_platform_risk_score   (0–100)  risk of Adobe native competitor (v6 NEW)
  - overall_score               (0–10, weighted composite)
  - score_rationales            dict     one brief rationale sentence per dimension
  - score_buckets               dict     rationales grouped into 5 category buckets (v6 NEW)

  Derived fields:
  - company_life_months         estimated months of runway if untouched
  - company_life_label          "Terminal" | "Declining" | "Stable" | "Growing / Durable"

  Financial fields:
  - down_payment            20% of asking_price
  - seller_finance_amount   80% of asking_price
  - monthly_debt_service    PMT(7% / 12, 60 periods, seller_finance_amount)
  - net_monthly_cashflow    monthly_net - monthly_debt_service
  - heloc_used              == down_payment
  - heloc_interest_monthly  heloc_used * 0.095 / 12
  - net_after_heloc         net_monthly_cashflow - heloc_interest_monthly
  - breakeven_months_with_draw  months to recoup down payment drawing $6K/mo salary (v6 NEW)

  Composite weights (v6, must sum to 1.0):
    cashflow              15%
    moat                  14%   ← includes SDK/IP/network/competitor bonuses
    ai_proof              13%
    competitor_analysis   10%   ← market crowding penalty
    company_life           9%   ← runway if untouched
    buy_vs_build           8%   ← rescaled from 0–10 → 0–100
    value_add              7%
    mitigation_score       7%   ← how well risks can be offset
    owner_neglect         10%   ← NEW: operator absence damage (inverted: lower neglect = higher contribution)
    adobe_platform_risk    5%   ← NEW: Adobe native competition risk (inverted)
    risk_score             2%   ← multi-factor risk, inverted (lower risk = higher contribution)
  Total: 100%

  Buy vs Build scoring:
  - "buy"    → score = max(moat_score / 10, 7.0)   buying justified when moat is deep
  - "build"  → score = max(10 - moat_score / 10, 3.0)  building better when moat is shallow
  - "hybrid" → score = 5.0 baseline
  - If buy_vs_build_score is manually set (>0), keep the manual value.

  Score Buckets (v6):
  - Financial          cashflow_score, buy_vs_build_score, breakeven_months_with_draw
  - Moat & Defense     moat_score, ai_proof_score, competitor_analysis_score, company_life_score
  - Risk & Mitigation  risk_score, mitigation_score
  - Platform Risk      adobe_platform_risk_score
  - Operator Profile   owner_neglect_score, value_add_score
"""

# ===========================================================================
# EVA DEAL INTELLIGENCE LEARNINGS  (append new entries chronologically)
# ===========================================================================
#
# LEARNING 001 — batch.ai / June 2026
# -----------------------------------------------------------------------
# Q: Why would users want batch.ai when Adobe offers batch features in enterprise?
#
# A: Adobe Firefly Creative Production (announced Oct 28 2025, private beta)
#    targets ENTERPRISE content teams at $1,000+/month minimum. It automates
#    campaign production, brand localization, and content supply chains for
#    marketing departments at large companies. The buyer is a CMO or content
#    ops team. batch.ai's buyer is an individual wedding/portrait photographer
#    charging $2,000/wedding who needs their gallery of 1,000 images edited
#    in 30 minutes in their personal style. These markets do not overlap.
#
#    Adobe LR Classic 15.3 (Apr 2026) added background AI for Denoise and
#    Super Resolution ONLY. It does NOT learn the photographer's edit style
#    and does NOT batch-apply user adjustments. It's a technical utility,
#    not a workflow automation tool.
#
#    batch.ai's real competitors are Aftershoot ($480/yr) and Imagen AI
#    ($810+/yr) — both STANDALONE APPS that require leaving Lightroom.
#    batch.ai is a plugin that lives INSIDE LR Classic. That single UX
#    advantage (zero context switching) is the primary reason photographers
#    describe it as "life-changing" in reviews.
#
# Q: Is Adobe enterprise competition the reason users are leaving?
#
# A: NO. Revenue decline ($13K -> $5K, -62%) is 100% marketing neglect.
#    Evidence:
#    - Trustpilot 4.8/5, 50 reviews, all from 2022-2023 when Shawn was active
#    - Reviews explicitly mention "Shawn" by name as personally responsive
#    - When Shawn went absent: Instagram went dormant, email list cold,
#      zero new acquisition, support response times degraded
#    - Product itself: Stripe still billing, SDK still functional,
#      active users still posting about it (Instagram Reel Nov 2025)
#    - Adobe enterprise launched AFTER the revenue decline began
#    - Decline curve tracks marketing silence, not product degradation
#
# MARKETING BUDGET SIGNAL:
#    No public ad spend data (private company). Growth was entirely organic
#    social — Shawn's personal brand driving word-of-mouth in the wedding
#    photography community via Instagram. When Shawn stopped posting,
#    the acquisition funnel closed completely. Zero paid acquisition history
#    means Day 1 post-acquisition: reactivate Instagram + email list.
#    Re-engagement cost: near zero. Revenue recovery ETA: 60-90 days.
#
# DEAL INTELLIGENCE RULE (encoded from this deal):
#    When a SaaS shows sharp revenue decline with intact product metrics
#    (Stripe still billing, core product functional, positive reviews still
#    visible), check the OWNER'S SOCIAL ACTIVITY TIMELINE before assuming
#    product or market failure. Revenue that tracks perfectly with the
#    founder's last Instagram post = marketing problem, not product problem.
#    Marketing problems are the most recoverable form of decline.
#    This pattern should RAISE value_add_score, not lower the offer price.
# ===========================================================================

from __future__ import annotations
import math
from datetime import datetime, timezone

from models import Deal

# ---------------------------------------------------------------------------
# Category constants
# ---------------------------------------------------------------------------

CATEGORY_MOAT_BONUS: dict[str, float] = {
    "Services": 15.0,
    "Education": 10.0,
    "SaaS": 5.0,
    "Content": 0.0,
    "Digital Products": -10.0,
}

# Competitor density penalty: fewer competitors = higher score
# These are baseline adjustments; fine-tuned per deal via num_competitors input
CATEGORY_COMPETITOR_BASE: dict[str, float] = {
    "Services": 60.0,    # human services = moderate competition
    "Education": 55.0,
    "SaaS": 50.0,        # default SaaS is crowded
    "Content": 40.0,     # content is commoditised
    "Digital Products": 35.0,
}

# Monthly revenue decay rate if untouched (% per month, no marketing/ops effort)
CATEGORY_DECAY_RATE: dict[str, float] = {
    "SaaS": 0.04,           # 4%/mo churn if neglected
    "Services": 0.06,
    "Education": 0.03,
    "Content": 0.07,
    "Digital Products": 0.08,
}

CATEGORY_AI_PROOF_BASE: dict[str, float] = {
    "Services": 85.0,
    "Education": 82.0,
    "SaaS": 75.0,
    "Content": 68.0,
    "Digital Products": 38.0,
}

CATEGORY_RISK_PENALTY: dict[str, float] = {
    "Digital Products": -20.0,
}

# Base risk exposure by category (0–100, higher = more risky)
CATEGORY_BASE_RISK: dict[str, float] = {
    "SaaS": 35.0,
    "Services": 40.0,
    "Education": 30.0,
    "Content": 55.0,
    "Digital Products": 65.0,
}

# Base mitigation potential by category (0–100, higher = easier to mitigate)
CATEGORY_BASE_MITIGATION: dict[str, float] = {
    "SaaS": 70.0,
    "Services": 60.0,
    "Education": 72.0,
    "Content": 50.0,
    "Digital Products": 40.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# PMT formula  (standard amortisation)
# ---------------------------------------------------------------------------

def _pmt(annual_rate: float, n_periods: int, principal: float) -> float:
    """Return the periodic payment for a fixed-rate loan.

    Args:
        annual_rate: Annual interest rate as a decimal (e.g. 0.07 for 7%).
        n_periods:   Number of payment periods (months).
        principal:   Loan principal.

    Returns:
        Monthly payment amount (positive).
    """
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / n_periods
    return principal * (r * (1 + r) ** n_periods) / ((1 + r) ** n_periods - 1)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _cashflow_score(monthly_net: float) -> float:
    """(monthly_net / 15000) * 100, capped at 100."""
    return _clamp((monthly_net / 15_000.0) * 100.0)


def _moat_score(
    age_years: float,
    category: str,
    num_competitors: int = 10,
    has_sdk_integration: bool = False,
    has_proprietary_data: bool = False,
    has_network_effect: bool = False,
) -> float:
    """Defensibility depth score.

    Base from age bracket + category bonus + structural moat bonuses:
    - SDK / API lock-in:      +15 pts
    - Proprietary data/IP:    +10 pts
    - Network effect:         +12 pts
    - Few competitors (<5):   +10 pts

    WHY THIS IS HARD TO REPLICATE (batch.ai case study):
    -------------------------------------------------------
    1. STYLE MEMORY ENGINE — The core AI learns a photographer's personal editing
       style from anchor images and replicates it across an entire gallery. This
       requires months of per-photographer training data and fine-tuning that a
       new entrant cannot shortcut. Each user's model is effectively unique.

    2. ADOBE LR CLASSIC SDK INTEGRATION — The plugin runs natively inside
       Lightroom Classic via the Lua-based SDK. Replicating this requires:
       (a) Adobe developer partner status (not open to anyone),
       (b) deep Lua SDK expertise (extremely rare skillset),
       (c) seamless UX that feels native — not a separate app.
       Adobe LR Classic SDK has ZERO deprecation signal through 2026.

    3. ADOBE FIREFLY CREATIVE PRODUCTION IS NOT A COMPETITOR —
       Released October 28, 2025 (private beta). Targets enterprise content
       teams running brand campaigns and localization at $1,000+/month minimum
       with enterprise sales agreements. batch.ai's market is individual
       professional photographers (wedding, portrait, commercial) at $30–130/month.
       These are COMPLETELY DIFFERENT buyers, budgets, and use cases.

    4. LR CLASSIC 15.3 BACKGROUND AI (April 2026) — Adds background processing
       for Denoise and Super Resolution ONLY. Does NOT replicate style, does NOT
       learn user editing preferences, does NOT batch-apply user adjustments.
       This is a noise reduction utility, not a workflow automation layer.

    5. SWITCHING COST — Photographers who have trained batch.ai on their style
       have sunk time into anchor editing sessions. Switching means retraining
       a new tool from scratch. High behavioral lock-in.

    6. TRUST MOAT — Trustpilot: 4.8/5 from 50 reviews, all from professional
       photographers. Users describe it as 'life-changing' and name Shawn
       personally. This community trust and brand equity takes years to build.

    7. AFTERSHOOT / IMAGEN AI COMPARISON — The real competitors (Aftershoot at
       $480/yr, Imagen at $810+/yr) are standalone apps that require leaving
       Lightroom. batch.ai works INSIDE LR Classic — zero workflow disruption.
       That in-app native experience is the primary differentiation.

    REPLICATION TIME ESTIMATE: 18–24 months minimum for a funded team.
    A solo developer cannot replicate the style engine + SDK integration + brand
    trust within a realistic acquisition horizon.
    """
    if age_years < 5:
        base = 40.0
    elif age_years < 10:
        base = 70.0
    else:
        base = 90.0

    bonus = CATEGORY_MOAT_BONUS.get(category, 0.0)
    sdk_bonus = 15.0 if has_sdk_integration else 0.0
    data_bonus = 10.0 if has_proprietary_data else 0.0
    network_bonus = 12.0 if has_network_effect else 0.0
    competitor_bonus = 10.0 if num_competitors < 5 else 0.0
    return _clamp(base + bonus + sdk_bonus + data_bonus + network_bonus + competitor_bonus)


def _ai_proof_score(age_years: float, category: str, current_score: float) -> float:
    """Category baseline + age trust bonus (+5 if age >= 5 years)."""
    base = CATEGORY_AI_PROOF_BASE.get(category, 70.0)
    age_bonus = 5.0 if age_years >= 5 else 0.0
    return _clamp(base + age_bonus)


def _risk_score(
    age_years: float,
    category: str,
    monthly_net: float,
    peak_monthly_net: float,
    num_competitors: int,
    has_sdk_integration: bool,
    single_owner_dependent: bool = False,
    revenue_declining: bool = False,
    financing_required: bool = True,
) -> tuple[float, list]:
    """Multi-factor risk exposure score (0–100, HIGHER = MORE RISK).

    Risk factors (additive penalties on base):
      - Young business (<3 years):          +15
      - Revenue declining vs peak (>30%):   +20
      - Single-owner dependent:             +15
      - Many competitors (>10):             +10
      - Financing required:                 +5
      - No SDK/IP moat:                     +10

    Returns (risk_score, risk_flags list)
    """
    flags = []
    base = CATEGORY_BASE_RISK.get(category, 45.0)

    if age_years < 3:
        base += 15.0
        flags.append(f"Young business ({age_years:.0f} yr) — limited operating track record")

    if peak_monthly_net > 0 and monthly_net < peak_monthly_net * 0.70:
        decline_pct = round((1 - monthly_net / peak_monthly_net) * 100)
        base += 20.0
        flags.append(f"Revenue {decline_pct}% below peak (${peak_monthly_net:,.0f}/mo) — needs recovery thesis")

    if single_owner_dependent:
        base += 15.0
        flags.append("Single-owner dependent — key-person risk on transition")

    if num_competitors > 10:
        base += 10.0
        flags.append(f"{num_competitors} competitors — crowded market increases churn risk")

    if financing_required:
        base += 5.0
        flags.append("Financing required — execution risk if lender terms change")

    if not has_sdk_integration:
        base += 10.0
        flags.append("No SDK/API lock-in — product replicability is higher")

    return _clamp(base), flags


def _mitigation_score(
    category: str,
    moat_score: float,
    risk_flags: list,
    has_sdk_integration: bool,
    has_proprietary_data: bool,
    monthly_net: float,
    peak_monthly_net: float,
    age_years: float,
    num_competitors: int,
) -> tuple[float, list]:
    """How well the identified risks can be offset by the acquirer (0–100, HIGHER = BETTER).

    Mitigation levers (additive bonuses on base):
      - Deep moat (>60):                    +15  (structural defense)
      - SDK/API lock-in:                    +10  (switching cost)
      - Proprietary data:                   +8   (irreplaceable asset)
      - Revenue recovery path clear:        +12  (marketing neglect is fixable)
      - Established business (>3yr):        +8   (ops playbook exists)
      - Tight niche (<=5 competitors):      +10  (pricing power)

    Returns (mitigation_score, mitigation_actions list)
    """
    actions = []
    base = CATEGORY_BASE_MITIGATION.get(category, 55.0)

    if moat_score > 60:
        base += 15.0
        actions.append("Leverage deep moat as competitive barrier — highlight SDK exclusivity in positioning")

    if has_sdk_integration:
        base += 10.0
        actions.append("Protect SDK integration as primary moat — negotiate transfer of Adobe partner agreement")

    if has_proprietary_data:
        base += 8.0
        actions.append("Lock proprietary datasets into exclusive licensing terms before close")

    if peak_monthly_net > 0 and monthly_net < peak_monthly_net * 0.85:
        base += 12.0
        actions.append("Revenue dip is marketing neglect — reactivate email list and Instagram within 30 days")

    if age_years >= 3:
        base += 8.0
        actions.append("Established ops playbook exists — request full SOP documentation in DD")

    if num_competitors <= 5:
        base += 10.0
        actions.append("Tight niche — raise prices 10–20% post-acquisition to capture margin compression")

    return _clamp(base), actions


def _competitor_analysis_score(category: str, num_competitors: int = 10) -> float:
    """Market crowding score — higher = less competitive = better for buyer.

    Starts from category baseline, then adjusts for actual competitor count:
      0–2   competitors: +30 pts  (near-monopoly niche)
      3–5   competitors: +15 pts  (tight niche)
      6–10  competitors:  +0 pts  (base)
      11–20 competitors: -15 pts  (crowded)
      21+   competitors: -30 pts  (commoditised)
    """
    base = CATEGORY_COMPETITOR_BASE.get(category, 50.0)
    if num_competitors <= 2:
        adjustment = 30.0
    elif num_competitors <= 5:
        adjustment = 15.0
    elif num_competitors <= 10:
        adjustment = 0.0
    elif num_competitors <= 20:
        adjustment = -15.0
    else:
        adjustment = -30.0
    return _clamp(base + adjustment)


def _company_life(
    monthly_net: float,
    category: str,
    moat_score: float,
    revenue_floor: float = 500.0,
) -> tuple[float, float, str]:
    """Estimate survival runway if the business is left completely untouched.

    Uses category decay rate, softened by moat strength:
      effective_decay = base_decay * (1 - moat_dampener)
      moat_dampener   = moat_score / 200  (max 50% reduction at moat=100)

    Returns:
        (company_life_months, company_life_score, company_life_label)

    Labels:
      < 12 months  → "Terminal"
      12–24 months → "Declining"
      24–48 months → "Stable"
      48+ months   → "Growing / Durable"
    """
    base_decay = CATEGORY_DECAY_RATE.get(category, 0.05)
    moat_dampener = moat_score / 200.0          # 0.0 – 0.5
    effective_decay = base_decay * (1.0 - moat_dampener)

    if effective_decay <= 0 or monthly_net <= revenue_floor:
        months = 0.0
    else:
        # geometric decay: revenue_floor = monthly_net * (1 - decay)^n
        # n = log(floor / net) / log(1 - decay)
        months = math.log(revenue_floor / monthly_net) / math.log(1.0 - effective_decay)
        months = max(0.0, months)

    # Score: 100 = 48+ months, 0 = 0 months
    score = _clamp((months / 48.0) * 100.0)

    if months < 12:
        label = "Terminal"
    elif months < 24:
        label = "Declining"
    elif months < 48:
        label = "Stable"
    else:
        label = "Growing / Durable"

    return round(months, 1), round(score, 2), label


def _buy_vs_build_score(decision: str, moat_score: float) -> float:
    """
    Derive buy_vs_build_score from decision and moat:
    - "buy"    → max(moat_score / 10, 7.0)
    - "build"  → max(10 - moat_score / 10, 3.0)
    - "hybrid" → 5.0

    BUY VS BUILD RATIONALE (batch.ai case study):
    -----------------------------------------------
    VERDICT: STRONG BUY — building this from scratch is not economically rational.

    WHY YOU CANNOT JUST BUILD IT:

    a) STYLE ENGINE BUILD COST
       Training a per-photographer style-learning AI requires a proprietary
       ML pipeline, labeled training data from thousands of galleries, and
       continuous model iteration. Estimated engineering cost: $200K–$400K
       and 12–18 months before first usable output. batch.ai is 4 years old
       and has already absorbed that cost.

    b) ADOBE PARTNER STATUS
       The LR Classic Lua SDK requires Adobe developer partner registration.
       This is an approval process — not an open API. A new build starts
       at zero and cannot guarantee access. batch.ai already has this.

    c) EXISTING USER BASE = TRAINING DATA FLYWHEEL
       Every photographer using batch.ai is generating labeled edit data
       that improves the style model. A greenfield build starts with zero
       training data. The product gets better with use — you cannot buy
       that compounding curve, only inherit it.

    d) BRAND TRUST = ACQUISITION CHANNEL
       batch.ai grew through Shawn's personal brand and word-of-mouth in
       the professional photography community. Photographers explicitly name
       Shawn in 5-star reviews. That referral channel took 4 years to build.
       A new build has no referral base, no SEO, no Trustpilot history.

    e) REVENUE DECLINE IS MARKETING, NOT PRODUCT
       The product itself is intact. Stripe is still billing. The SDK still
       works. What failed was acquisition — Instagram went dark, email list
       went cold. A new owner with marketing discipline recovers $13K/mo in
       ~90 days. Building a competing product takes 18–24 months just to
       reach feature parity, then another 12 months to acquire a user base.

    f) REAL COMPETITOR BENCHMARK
       Aftershoot: $480/yr, 100,000+ users, 164+ countries — took 6+ years.
       Imagen AI: $810+/yr, standalone app — took 5+ years.
       Both are OUTSIDE Lightroom. batch.ai is INSIDE Lightroom.
       Acquiring batch.ai = skipping 4–6 years of development and distribution.

    BOTTOM LINE: At $179K asking price, you are buying:
    • 4 years of ML model development
    • Adobe LR Classic SDK partner access
    • Style engine trained on thousands of real photography sessions
    • 4.8/5 Trustpilot brand trust with professional photographers
    • Existing recurring Stripe subscriber base
    • A 90-day recoverable revenue decline from marketing neglect
    • A whitelabel-ready SaaS module with clear expansion path
    Total cost to build equivalent: $400K–$700K + 3–4 years.
    """
    if decision == "buy":
        return max(moat_score / 10.0, 7.0)
    elif decision == "build":
        return max(10.0 - moat_score / 10.0, 3.0)
    else:  # hybrid
        return 5.0


# ---------------------------------------------------------------------------
# v6 NEW: Owner Neglect Score
# ---------------------------------------------------------------------------

def _owner_neglect_score(
    monthly_net: float,
    peak_monthly_net: float,
    owner_neglect_months: int = 0,
    owner_is_sole_operator: bool = False,
    category: str = "SaaS",
) -> tuple[float, str]:
    """Damage score from owner absence (0–100, HIGHER = more damage from neglect).

    Scoring model:
      - Revenue decline from peak drives the base damage signal
      - Months of neglect amplifies the damage (each month beyond 3 adds +3, capped at +20)
      - Sole operator dependency amplifies further (+15)
      - SaaS has auto-pilot resilience: billing, core product survive; what decays is
        customer acquisition, support quality, and community engagement

    Inverted for composite: low neglect damage = higher contribution to overall score.

    Returns (owner_neglect_score, rationale_string)
    """
    _peak = peak_monthly_net if peak_monthly_net > 0 else monthly_net

    # Base damage from revenue decline
    if _peak > 0 and monthly_net < _peak:
        decline_pct = (1.0 - monthly_net / _peak) * 100.0
        base = _clamp(decline_pct * 1.2)  # amplify: 62% decline → ~74 base
    else:
        base = 0.0

    # Duration penalty: each month beyond 3 adds +3, capped at +20
    if owner_neglect_months > 3:
        duration_penalty = min((owner_neglect_months - 3) * 3.0, 20.0)
        base += duration_penalty

    # Sole operator penalty
    if owner_is_sole_operator:
        base += 15.0

    score = _clamp(base)

    # Determine what survived vs what decayed (SaaS-specific insight)
    survived_items = []
    decayed_items = []

    if category == "SaaS":
        survived_items = [
            "Stripe subscription billing (recurring charges continued uninterrupted)",
            "Core product functionality (Adobe SDK integration remained operational)",
            "Existing power users who derive independent workflow value",
        ]
        decayed_items = [
            "Instagram presence (dormant → stalled new subscriber acquisition)",
            "Email list engagement (zero re-engagement campaigns → list went cold)",
            "New customer acquisition (zero paid/organic acquisition activity)",
            "Support response times (degraded → increased churn friction)",
            "Product communication (no changelog, updates, or user touchpoints)",
        ]

    survived_str = "; ".join(survived_items) if survived_items else "core product"
    decayed_str = "; ".join(decayed_items) if decayed_items else "marketing and acquisition"

    decline_pct_display = round((1.0 - monthly_net / _peak) * 100.0) if _peak > 0 else 0

    rationale = (
        f"Owner absent ~{owner_neglect_months} months; revenue slid {decline_pct_display}% "
        f"(${_peak:,.0f} → ${monthly_net:,.0f}/mo). "
        f"SURVIVED on auto-pilot: {survived_str}. "
        f"DECAYED without attention: {decayed_str}. "
        + (
            "Damage is entirely marketing/attention neglect — product core is intact; "
            "recovery thesis is credible within 60–90 days of active ownership."
            if score < 60 else
            "Significant neglect damage — recovery requires structured 90-day sprint "
            "covering email reactivation, social rebuilding, and support SLA restoration."
        )
    )

    return round(score, 2), rationale


# ---------------------------------------------------------------------------
# v6 NEW: Adobe Platform Risk Score
# ---------------------------------------------------------------------------

def _adobe_platform_risk_score(
    has_sdk_integration: bool,
    adobe_native_overlap_pct: float = 0.0,
    category: str = "SaaS",
) -> tuple[float, str]:
    """Risk that Adobe releases a native competing feature set (0–100, HIGHER = more risk).

    Research-backed scoring (June 2026):
      - Adobe LR Classic background batch AI (April 2026) = native overlap exists
      - Adobe Experience Cloud AI Agents = B2B marketing, DIFFERENT product line
      - Adobe Firefly Bulk Actions = enterprise content teams, NOT photographer prosumer market
      - LR Classic Lua SDK: zero deprecation signal through 2026
      - Real threat: native batch for basic use cases; mitigation = orchestration layer + multi-DAW

    Scoring factors:
      - Native overlap already exists (adobe_native_overlap_pct > 0):  base = overlap_pct * 60
      - SDK deprecation risk (currently LOW — penalised as low signal):  +10 if no SDK integration
      - Orchestration layer value (what SURVIVES):  mitigates score by -20 if has_sdk_integration
      - Market separation (Firefly targets enterprise, not batch.ai's prosumer niche): -10

    Returns (adobe_platform_risk_score, rationale_string)
    """
    # Base: proportional to actual native feature overlap percentage
    base = adobe_native_overlap_pct * 60.0  # 30% overlap → 18 base

    # SDK deprecation risk — current signal is LOW but non-zero
    if not has_sdk_integration:
        base += 10.0  # no SDK means product is more vulnerable

    # Adobe's "AI agents" are in Experience Cloud (B2B marketing) — completely separate
    # Firefly Bulk Actions targets enterprise content teams, not photographers
    # Both are market-separated from batch.ai's prosumer niche → risk reduction
    base -= 10.0  # market separation discount

    # Having SDK integration means batch.ai has an orchestration layer Adobe can't easily replicate
    if has_sdk_integration:
        base -= 20.0  # orchestration layer is durable even if Adobe goes native

    score = _clamp(base)

    # Build rationale with survival analysis
    overlap_pct_display = round(adobe_native_overlap_pct * 100)
    survived_if_adobe_native = [
        "Workflow automation layer (multi-step sequences LR Classic can't natively chain)",
        "Export pipeline & format routing (Photomechanic-style delivery automation)",
        "Third-party preset management & batch application",
        "Cross-DAW portability (expansion to Capture One, Darktable reduces Adobe dependency)",
        "Photographer UX that existing users already know and trust",
        "API integration hooks that connect LR Classic to external services",
    ]

    mitigation_actions = [
        "Position batch.ai as orchestration layer ON TOP OF LR Classic — not a replacement",
        "Accelerate Capture One integration to reduce single-platform dependency",
        "Expand to Darktable (open-source) to serve users priced out of Adobe ecosystem",
        "Negotiate Adobe partner/ISV agreement to formalize SDK access",
    ]

    survived_str = "; ".join(survived_if_adobe_native[:3])  # top 3 for brevity
    mitigation_str = "; ".join(mitigation_actions[:2])

    rationale = (
        f"Adobe native overlap currently ~{overlap_pct_display}% of batch.ai feature set "
        f"(April 2026: background batch AI in LR Classic). "
        f"Adobe's 'AI agents' are in Experience Cloud (B2B marketing) — separate product line; "
        f"Firefly Bulk Actions targets enterprise, not batch.ai's prosumer photographers. "
        f"LR Classic SDK (Lua) has zero deprecation signal through 2026. "
        f"SURVIVES even if Adobe goes fully native: {survived_str}. "
        f"MITIGATION: {mitigation_str}. "
        + (
            "Risk is manageable — Adobe's native push validates the market but "
            "batch.ai's orchestration layer is defensible."
            if score < 40 else
            "Moderate platform risk — diversification to Capture One + Darktable "
            "is the critical risk reduction lever; execute within 6 months of acquisition."
        )
    )

    return round(score, 2), rationale


# ---------------------------------------------------------------------------
# v6 NEW: Breakeven with $6K/mo Draw
# ---------------------------------------------------------------------------

def _breakeven_with_draw(
    down_payment: float,
    monthly_net: float,
    monthly_debt_service: float,
    heloc_interest_monthly: float,
    monthly_salary_draw: float = 6000.0,
) -> float:
    """Compute months to recoup down payment while drawing a monthly salary.

    Model:
      - Each month: free_cashflow = monthly_net - debt_service - heloc_interest - salary_draw
      - If free_cashflow > 0, it accumulates toward recovering the down payment
      - If free_cashflow <= 0, no accumulation that month (no negative carry tracked here)
      - Returns the month number when cumulative cashflow >= down_payment
      - Hard cap at 120 months (10 years) — if not recoverable, returns 120.0

    Returns: breakeven_months (float)
    """
    if down_payment <= 0:
        return 0.0

    cumulative = 0.0
    for month in range(1, 121):
        free_cf = monthly_net - monthly_debt_service - heloc_interest_monthly - monthly_salary_draw
        if free_cf > 0:
            cumulative += free_cf
        if cumulative >= down_payment:
            return float(month)

    return 120.0  # not recoverable within 10 years


# ---------------------------------------------------------------------------
# v6 NEW: Score Buckets
# ---------------------------------------------------------------------------

def _bucket_rationales(
    score_rationales: dict,
    owner_neglect_rationale: str,
    adobe_platform_risk_rationale: str,
    breakeven_months: float,
    down_payment: float,
    monthly_salary_draw: float,
) -> dict:
    """Group score rationales into 5 category buckets.

    Buckets:
      Financial          — cashflow, buy_vs_build, breakeven analysis
      Moat & Defense     — moat, ai_proof, competitor_analysis, company_life
      Risk & Mitigation  — risk, mitigation
      Platform Risk      — adobe_platform_risk (v6 new)
      Operator Profile   — owner_neglect (v6 new), value_add
    """
    buckets = {
        "Financial": {
            "cashflow_score": score_rationales.get("cashflow_score", ""),
            "buy_vs_build_score": score_rationales.get("buy_vs_build_score", ""),
            "breakeven_with_draw": (
                f"Drawing ${monthly_salary_draw:,.0f}/mo salary: down payment of "
                f"${down_payment:,.0f} recovered in ~{breakeven_months:.0f} months "
                f"({breakeven_months / 12:.1f} years). "
                + (
                    "Strong cashflow recovery even with owner draw — acquisition pays itself off quickly."
                    if breakeven_months <= 12 else
                    "Moderate payback period — cashflow covers draw but requires patience on capital return."
                    if breakeven_months <= 24 else
                    "Extended payback — consider reducing draw in early months to accelerate recovery."
                )
            ),
        },
        "Moat & Defense": {
            "moat_score": score_rationales.get("moat_score", ""),
            "ai_proof_score": score_rationales.get("ai_proof_score", ""),
            "competitor_analysis_score": score_rationales.get("competitor_analysis_score", ""),
            "company_life_score": score_rationales.get("company_life_score", ""),
        },
        "Risk & Mitigation": {
            "risk_score": score_rationales.get("risk_score", ""),
            "mitigation_score": score_rationales.get("mitigation_score", ""),
        },
        "Platform Risk": {
            "adobe_platform_risk_score": adobe_platform_risk_rationale,
        },
        "Operator Profile": {
            "owner_neglect_score": owner_neglect_rationale,
            "value_add_score": score_rationales.get("value_add_score", ""),
        },
    }
    return buckets


# ---------------------------------------------------------------------------
# v6 UPDATED: Composite score (11 parameters, sums to 100%)
# ---------------------------------------------------------------------------

def _overall_score(
    cashflow: float,
    moat: float,
    ai_proof: float,
    value_add: float,
    risk_exposure: float,       # 0–100, HIGHER = MORE RISK — inverted for composite
    mitigation: float,          # 0–100, HIGHER = BETTER mitigation
    competitor_analysis: float,
    company_life: float,
    buy_vs_build: float,        # 0–10 scale — rescaled to 0–100 internally
    owner_neglect: float,       # 0–100, HIGHER = MORE DAMAGE — inverted for composite
    adobe_platform_risk: float, # 0–100, HIGHER = MORE RISK — inverted for composite
) -> float:
    """Weighted composite on 0–100 scale, then normalised to 0–10.

    Weights (v6):
      cashflow                15%
      moat                    14%
      ai_proof                13%
      competitor_analysis     10%
      company_life             9%
      buy_vs_build             8%  (rescaled: score * 10 → 0–100)
      value_add                7%
      mitigation               7%
      owner_neglect_inverted  10%  (100 - owner_neglect: less damage = higher score)
      adobe_risk_inverted      5%  (100 - adobe_platform_risk: lower risk = higher score)
      risk_inverted            2%  (100 - risk_exposure: lower risk = higher contribution)
    Total: 100%
    """
    buy_vs_build_normalized = buy_vs_build * 10.0    # 0–10 → 0–100
    risk_inverted = 100.0 - risk_exposure             # invert
    owner_neglect_inverted = 100.0 - owner_neglect    # invert: less damage = better
    adobe_risk_inverted = 100.0 - adobe_platform_risk # invert: less risk = better

    composite = (
        cashflow                    * 0.15
        + moat                      * 0.14
        + ai_proof                  * 0.13
        + competitor_analysis       * 0.10
        + company_life              * 0.09
        + buy_vs_build_normalized   * 0.08
        + value_add                 * 0.07
        + mitigation                * 0.07
        + owner_neglect_inverted    * 0.10
        + adobe_risk_inverted       * 0.05
        + risk_inverted             * 0.02
    )
    # Normalise 0–100 → 0–10
    return round(_clamp(composite / 10.0, 0.0, 10.0), 2)


# ---------------------------------------------------------------------------
# Rationale generator (v5 base + v6 additions)
# ---------------------------------------------------------------------------

def _build_rationales(
    deal_name: str,
    category: str,
    age_years: float,
    monthly_net: float,
    asking_price: float,
    num_competitors: int,
    has_sdk_integration: bool,
    has_proprietary_data: bool,
    has_network_effect: bool,
    cashflow_score: float,
    moat_score: float,
    ai_proof_score: float,
    value_add_score: float,
    buy_vs_build_score: float,
    buy_vs_build_decision: str,
    risk_score: float,
    risk_flags: list,
    mitigation_score: float,
    mitigation_actions: list,
    competitor_analysis_score: float,
    company_life_score: float,
    company_life_months: float,
    company_life_label: str,
) -> dict:
    """Generate one plain-English rationale sentence per scoring dimension."""

    rationales = {}

    # Cashflow
    annual_net = monthly_net * 12
    multiple = round(asking_price / annual_net, 1) if annual_net > 0 else 0
    rationales["cashflow_score"] = (
        f"Generating ${monthly_net:,.0f}/mo (${annual_net:,.0f}/yr) at a {multiple}x annual multiple — "
        + ("strong cashflow engine relative to asking price."
           if cashflow_score >= 60 else
           "below benchmark but cash-flow positive; recovery upside justifies entry."
           if cashflow_score >= 30 else
           "low current yield; thesis depends entirely on growth recovery.")
    )

    # Moat
    moat_drivers = []
    if has_sdk_integration:    moat_drivers.append("SDK/API lock-in (+15)")
    if has_proprietary_data:   moat_drivers.append("proprietary data/IP (+10)")
    if has_network_effect:     moat_drivers.append("network effect (+12)")
    if num_competitors < 5:    moat_drivers.append(f"only {num_competitors} competitor(s) in niche (+10)")
    driver_str = ", ".join(moat_drivers) if moat_drivers else "category and age only"
    rationales["moat_score"] = (
        f"{age_years:.0f}-year-old {category} business; defensibility driven by {driver_str} — "
        + ("deep moat, difficult to replicate within 12 months."
           if moat_score >= 75 else
           "moderate moat, replication possible but non-trivial."
           if moat_score >= 50 else
           "shallow moat, vulnerable to fast followers.")
    )

    # AI-Proof
    rationales["ai_proof_score"] = (
        f"{category} category baseline gives {ai_proof_score:.0f}/100 AI disruption resistance — "
        + ("well-insulated; AI tools augment rather than replace this niche."
           if ai_proof_score >= 75 else
           "moderate exposure; monitor AI tooling in this space over 12–18 months."
           if ai_proof_score >= 55 else
           "high AI disruption risk; thesis requires a strong differentiation moat.")
    )

    # Competitor Analysis
    rationales["competitor_analysis_score"] = (
        f"{num_competitors} direct competitor(s) in the {category} niche — "
        + ("near-monopoly positioning; pricing power and margin protection are high."
           if num_competitors <= 2 else
           "tight competitive field; differentiation is the growth lever."
           if num_competitors <= 5 else
           "moderately crowded; acquirer must own a clear positioning wedge."
           if num_competitors <= 10 else
           "crowded market; sustainable moat is prerequisite for this acquisition.")
    )

    # Company Life
    rationales["company_life_score"] = (
        f"If left completely untouched, estimated {company_life_months:.0f} months of runway — "
        f"classified as '{company_life_label}'. "
        + ("Business can survive benign neglect; moat slows churn decay significantly."
           if company_life_label in ("Growing / Durable", "Stable") else
           "Revenue will erode within 2 years without active ownership; hands-on operator needed."
           if company_life_label == "Declining" else
           "Terminal trajectory without immediate intervention; high-urgency turnaround required.")
    )

    # Buy vs Build
    bvb_label = buy_vs_build_decision.upper()
    rationales["buy_vs_build_score"] = (
        f"Decision: {bvb_label} — score {buy_vs_build_score:.1f}/10. "
        + (f"Buying justified: moat depth ({moat_score:.0f}/100) makes replication 18–24 months minimum "
           f"for a funded team. Key barriers: (1) proprietary style-learning AI engine requires "
           f"$200K–$400K to rebuild from scratch; (2) Adobe LR Classic SDK partner access is an "
           f"approval-gated process, not open to new entrants; (3) existing user base is a training "
           f"data flywheel that compounds with use — cannot be replicated, only inherited; "
           f"(4) real competitors (Aftershoot $480/yr, Imagen $810+/yr) are outside Lightroom; "
           f"batch.ai runs INSIDE LR Classic — that native workflow position took 4 years to build. "
           f"Adobe Firefly Creative Production (Oct 2025) targets enterprise teams at $1K+/mo — "
           f"a completely different buyer than batch.ai's prosumer photographers."
           if buy_vs_build_decision == "buy" else
           f"Building justified: shallow moat ({moat_score:.0f}/100) means a greenfield build could "
           f"match this product at lower cost within 6–12 months."
           if buy_vs_build_decision == "build" else
           f"Hybrid approach: consider acquiring the customer base or IP while rebuilding the tech stack.")
    )

    # Value Add
    rationales["value_add_score"] = (
        f"Score {value_add_score:.0f}/100 — "
        + ("significant upside available via marketing reactivation, affiliate program, and annual plan upsell."
           if value_add_score >= 65 else
           "moderate upside; product is mature, gains come from operational efficiency."
           if value_add_score >= 40 else
           "limited value-add runway; product requires significant investment to move the needle.")
    )

    # Risk
    rationales["risk_score"] = (
        f"{len(risk_flags)} risk factor(s) identified — exposure score {risk_score:.0f}/100 "
        f"(higher = more exposed). "
        + ("High risk exposure; acquisition requires strong mitigation plan and tight DD."
           if risk_score >= 65 else
           "Moderate risk; manageable with proper transition planning and DD."
           if risk_score >= 40 else
           "Low risk profile; business is structurally sound with limited downside triggers.")
    )

    # Mitigation
    rationales["mitigation_score"] = (
        f"{len(mitigation_actions)} mitigation lever(s) available — mitigation score {mitigation_score:.0f}/100. "
        + ("Strong offset capability; most risks can be neutralized within 90 days of acquisition."
           if mitigation_score >= 70 else
           "Moderate mitigation; key risks addressable but require deliberate execution."
           if mitigation_score >= 50 else
           "Limited mitigation options; risk acceptance is the primary strategy.")
    )

    return rationales


# ---------------------------------------------------------------------------
# Public entry point (v6)
# ---------------------------------------------------------------------------

def analyze_deal(
    deal: Deal,
    num_competitors: int = 10,
    has_sdk_integration: bool = False,
    has_proprietary_data: bool = False,
    has_network_effect: bool = False,
    single_owner_dependent: bool = False,
    revenue_declining: bool = False,
    peak_monthly_net: float = 0.0,
    financing_required: bool = True,
    revenue_floor: float = 500.0,
    # v6 NEW parameters
    owner_neglect_months: int = 0,
    owner_is_sole_operator: bool = False,
    adobe_native_overlap_pct: float = 0.0,
    monthly_salary_draw: float = 6000.0,
) -> Deal:
    """Compute all scores, rationales, financial fields, and buckets; return an updated Deal copy.

    Parameters (v6):
        num_competitors           Number of direct competitors in the niche (default 10).
        has_sdk_integration       True if the business has a 3rd-party SDK/API lock-in.
        has_proprietary_data      True if the business holds proprietary datasets or IP.
        has_network_effect        True if value compounds as user base grows.
        single_owner_dependent    True if the business relies heavily on the current owner.
        revenue_declining         True if revenue has been declining trend (not just below peak).
        peak_monthly_net          Peak monthly net profit ever recorded (for decline % calculation).
        financing_required        True if acquisition requires external financing.
        revenue_floor             Monthly revenue threshold below which business is considered dead.
        owner_neglect_months      Number of months owner has been absent/neglectful (v6).
        owner_is_sole_operator    True if owner was sole operator (v6).
        adobe_native_overlap_pct  Fraction of features now available natively in LR Classic (v6).
        monthly_salary_draw       Monthly owner draw to use in breakeven calculation (default $6K).
    """
    d = deal.model_copy(deep=True)
    _peak = peak_monthly_net if peak_monthly_net > 0 else d.monthly_net

    # ---- scoring ----
    d.cashflow_score = round(_cashflow_score(d.monthly_net), 2)

    d.moat_score = round(
        _moat_score(
            d.age_years,
            d.category,
            num_competitors=num_competitors,
            has_sdk_integration=has_sdk_integration,
            has_proprietary_data=has_proprietary_data,
            has_network_effect=has_network_effect,
        ),
        2,
    )

    # ai_proof_score: use provided value if non-zero, else compute
    if d.ai_proof_score == 0.0:
        d.ai_proof_score = round(_ai_proof_score(d.age_years, d.category, d.ai_proof_score), 2)

    # value_add_score: preserve if non-zero, else default 70
    if d.value_add_score == 0.0:
        d.value_add_score = 70.0

    # buy_vs_build_score: preserve if manually set (>0), else compute from decision
    if d.buy_vs_build_score == 0.0:
        d.buy_vs_build_score = round(
            _buy_vs_build_score(d.buy_vs_build_decision, d.moat_score), 2
        )

    # risk: multi-factor, returns (score, flags)
    raw_risk, risk_flags = _risk_score(
        age_years=d.age_years,
        category=d.category,
        monthly_net=d.monthly_net,
        peak_monthly_net=_peak,
        num_competitors=num_competitors,
        has_sdk_integration=has_sdk_integration,
        single_owner_dependent=single_owner_dependent,
        revenue_declining=revenue_declining,
        financing_required=financing_required,
    )
    d.risk_score = round(raw_risk, 2)
    d.risk_flags = risk_flags

    # mitigation: returns (score, actions)
    raw_mitigation, mitigation_actions = _mitigation_score(
        category=d.category,
        moat_score=d.moat_score,
        risk_flags=risk_flags,
        has_sdk_integration=has_sdk_integration,
        has_proprietary_data=has_proprietary_data,
        monthly_net=d.monthly_net,
        peak_monthly_net=_peak,
        age_years=d.age_years,
        num_competitors=num_competitors,
    )
    d.mitigation_score = round(raw_mitigation, 2)
    d.mitigation_actions = mitigation_actions

    # competitor_analysis_score: compute if not manually set
    if d.competitor_analysis_score == 0.0:
        d.competitor_analysis_score = round(
            _competitor_analysis_score(d.category, num_competitors), 2
        )

    # company_life: always derived (reflects current state of the deal)
    months, life_score, life_label = _company_life(
        d.monthly_net, d.category, d.moat_score, revenue_floor
    )
    d.company_life_months = months
    d.company_life_score = life_score
    d.company_life_label = life_label

    # v6: owner neglect score
    owner_neglect_raw, owner_neglect_rationale = _owner_neglect_score(
        monthly_net=d.monthly_net,
        peak_monthly_net=_peak,
        owner_neglect_months=owner_neglect_months,
        owner_is_sole_operator=owner_is_sole_operator,
        category=d.category,
    )
    d.owner_neglect_score = owner_neglect_raw

    # v6: adobe platform risk score
    adobe_risk_raw, adobe_platform_risk_rationale = _adobe_platform_risk_score(
        has_sdk_integration=has_sdk_integration,
        adobe_native_overlap_pct=adobe_native_overlap_pct,
        category=d.category,
    )
    d.adobe_platform_risk_score = adobe_risk_raw

    # overall score — v6: 11 parameters, rebalanced weights
    d.overall_score = _overall_score(
        d.cashflow_score,
        d.moat_score,
        d.ai_proof_score,
        d.value_add_score,
        d.risk_score,
        d.mitigation_score,
        d.competitor_analysis_score,
        d.company_life_score,
        d.buy_vs_build_score,
        d.owner_neglect_score,
        d.adobe_platform_risk_score,
    )

    # ---- financial analysis ----
    d.down_payment = round(d.asking_price * 0.20, 2)
    d.seller_finance_amount = round(d.asking_price * 0.80, 2)
    d.monthly_debt_service = round(_pmt(0.07, 60, d.seller_finance_amount), 2)
    d.net_monthly_cashflow = round(d.monthly_net - d.monthly_debt_service, 2)
    d.heloc_used = d.down_payment
    d.heloc_interest_monthly = round(d.heloc_used * 0.095 / 12.0, 2)
    d.net_after_heloc = round(d.net_monthly_cashflow - d.heloc_interest_monthly, 2)

    # v6: breakeven with $6K draw
    d.breakeven_months_with_draw = _breakeven_with_draw(
        down_payment=d.down_payment,
        monthly_net=d.monthly_net,
        monthly_debt_service=d.monthly_debt_service,
        heloc_interest_monthly=d.heloc_interest_monthly,
        monthly_salary_draw=monthly_salary_draw,
    )

    # ---- rationales (auto-generated, one sentence per dimension) ----
    d.score_rationales = _build_rationales(
        deal_name=d.name,
        category=d.category,
        age_years=d.age_years,
        monthly_net=d.monthly_net,
        asking_price=d.asking_price,
        num_competitors=num_competitors,
        has_sdk_integration=has_sdk_integration,
        has_proprietary_data=has_proprietary_data,
        has_network_effect=has_network_effect,
        cashflow_score=d.cashflow_score,
        moat_score=d.moat_score,
        ai_proof_score=d.ai_proof_score,
        value_add_score=d.value_add_score,
        buy_vs_build_score=d.buy_vs_build_score,
        buy_vs_build_decision=d.buy_vs_build_decision,
        risk_score=d.risk_score,
        risk_flags=d.risk_flags,
        mitigation_score=d.mitigation_score,
        mitigation_actions=d.mitigation_actions,
        competitor_analysis_score=d.competitor_analysis_score,
        company_life_score=d.company_life_score,
        company_life_months=d.company_life_months,
        company_life_label=d.company_life_label,
    )

    # v6: bucket rationales into 5 categories
    d.score_buckets = _bucket_rationales(
        score_rationales=d.score_rationales,
        owner_neglect_rationale=owner_neglect_rationale,
        adobe_platform_risk_rationale=adobe_platform_risk_rationale,
        breakeven_months=d.breakeven_months_with_draw,
        down_payment=d.down_payment,
        monthly_salary_draw=monthly_salary_draw,
    )

    # stamp updated_at
    d.updated_at = datetime.now(timezone.utc).isoformat()

    return d
