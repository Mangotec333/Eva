"""
EVA Deal Scout — Scoring & Financial Analysis Engine (v5)
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
  - overall_score               (0–10, weighted composite)
  - score_rationales            dict     one brief rationale sentence per dimension

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

  Composite weights (must sum to 1.0):
    cashflow              17%
    moat                  16%   ← includes SDK/IP/network/competitor bonuses
    ai_proof              15%
    competitor_analysis   12%   ← market crowding penalty
    company_life          10%   ← runway if untouched
    buy_vs_build           9%   ← rescaled from 0–10 → 0–100
    value_add              8%
    mitigation_score       8%   ← NEW: how well risks can be offset
    risk_score             5%   ← ENHANCED: multi-factor, inverted (lower risk = higher contribution)
  Total: 100%

  Buy vs Build scoring:
  - "buy"    → score = max(moat_score / 10, 7.0)   buying justified when moat is deep
  - "build"  → score = max(10 - moat_score / 10, 3.0)  building better when moat is shallow
  - "hybrid" → score = 5.0 baseline
  - If buy_vs_build_score is manually set (>0), keep the manual value.
"""

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
    """
    if decision == "buy":
        return max(moat_score / 10.0, 7.0)
    elif decision == "build":
        return max(10.0 - moat_score / 10.0, 3.0)
    else:  # hybrid
        return 5.0


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
) -> float:
    """Weighted composite on 0–100 scale, then normalised to 0–10.

    Weights (v5):
      cashflow                17%
      moat                    16%
      ai_proof                15%
      competitor_analysis     12%
      company_life            10%
      buy_vs_build             9%  (rescaled: score * 10 → 0–100)
      value_add                8%
      mitigation               8%
      risk_inverted            5%  (100 - risk_exposure: lower risk = higher score)
    Total: 100%
    """
    buy_vs_build_normalized = buy_vs_build * 10.0   # 0–10 → 0–100
    risk_inverted = 100.0 - risk_exposure           # invert: low risk = high contribution
    composite = (
        cashflow                  * 0.17
        + moat                    * 0.16
        + ai_proof                * 0.15
        + competitor_analysis     * 0.12
        + company_life            * 0.10
        + buy_vs_build_normalized * 0.09
        + value_add               * 0.08
        + mitigation              * 0.08
        + risk_inverted           * 0.05
    )
    # Normalise 0–100 → 0–10
    return round(_clamp(composite / 10.0, 0.0, 10.0), 2)


# ---------------------------------------------------------------------------
# Rationale generator
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
        + (f"Buying justified: moat depth ({moat_score:.0f}/100) makes replication expensive and slow; "
           f"acquiring proven revenue beats a cold start."
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
# Public entry point
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
) -> Deal:
    """Compute all scores, rationales, and financial fields; return an updated Deal copy.

    Parameters (v5):
        num_competitors         Number of direct competitors in the niche (default 10).
        has_sdk_integration     True if the business has a 3rd-party SDK/API lock-in.
        has_proprietary_data    True if the business holds proprietary datasets or IP.
        has_network_effect      True if value compounds as user base grows.
        single_owner_dependent  True if the business relies heavily on the current owner.
        revenue_declining       True if revenue has been declining trend (not just below peak).
        peak_monthly_net        Peak monthly net profit ever recorded (for decline % calculation).
        financing_required      True if acquisition requires external financing.
        revenue_floor           Monthly revenue threshold below which business is considered dead.
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

    # overall score — v5: includes mitigation + inverted risk
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

    # ---- financial analysis ----
    d.down_payment = round(d.asking_price * 0.20, 2)
    d.seller_finance_amount = round(d.asking_price * 0.80, 2)
    d.monthly_debt_service = round(_pmt(0.07, 60, d.seller_finance_amount), 2)
    d.net_monthly_cashflow = round(d.monthly_net - d.monthly_debt_service, 2)
    d.heloc_used = d.down_payment
    d.heloc_interest_monthly = round(d.heloc_used * 0.095 / 12.0, 2)
    d.net_after_heloc = round(d.net_monthly_cashflow - d.heloc_interest_monthly, 2)

    # stamp updated_at
    d.updated_at = datetime.now(timezone.utc).isoformat()

    return d
