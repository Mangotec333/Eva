"""
EVA Deal Scout — Scoring & Financial Analysis Engine (v3)
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

  Derived fields:
  - company_life_months         estimated months of runway if untouched
  - company_life_label          "Terminal" | "Declining" | "Stable" | "Growing"

  Financial fields:
  - down_payment            20% of asking_price
  - seller_finance_amount   80% of asking_price
  - monthly_debt_service    PMT(7% / 12, 60 periods, seller_finance_amount)
  - net_monthly_cashflow    monthly_net - monthly_debt_service
  - heloc_used              == down_payment
  - heloc_interest_monthly  heloc_used * 0.095 / 12
  - net_after_heloc         net_monthly_cashflow - heloc_interest_monthly

  Composite weights (must sum to 1.0):
    cashflow            20%
    moat                18%   ← enhanced: now includes SDK/IP/network depth
    ai_proof            18%
    competitor_analysis 14%   ← NEW: market crowding penalty
    company_life        12%   ← NEW: runway if untouched
    value_add           10%
    risk                 8%

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


def _risk_score(age_years: float, category: str) -> float:
    """min(age_years * 8, 90) - 20 if Digital Products."""
    base = min(age_years * 8.0, 90.0)
    penalty = CATEGORY_RISK_PENALTY.get(category, 0.0)
    return _clamp(base + penalty)


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
    risk: float,
    competitor_analysis: float,
    company_life: float,
) -> float:
    """Weighted composite on 0–100 scale, then normalised to 0–10.

    Weights (v3):
      cashflow              20%
      moat                  18%
      ai_proof              18%
      competitor_analysis   14%
      company_life          12%
      value_add             10%
      risk                   8%
    Total: 100%
    """
    composite = (
        cashflow            * 0.20
        + moat              * 0.18
        + ai_proof          * 0.18
        + competitor_analysis * 0.14
        + company_life      * 0.12
        + value_add         * 0.10
        + risk              * 0.08
    )
    # Normalise 0–100 → 0–10
    return round(_clamp(composite / 10.0, 0.0, 10.0), 2)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_deal(
    deal: Deal,
    num_competitors: int = 10,
    has_sdk_integration: bool = False,
    has_proprietary_data: bool = False,
    has_network_effect: bool = False,
    revenue_floor: float = 500.0,
) -> Deal:
    """Compute all scores and financial fields; return an updated Deal copy.

    New optional parameters (v3):
        num_competitors       Number of direct competitors in the niche (default 10).
        has_sdk_integration   True if the business has a 3rd-party SDK/API lock-in.
        has_proprietary_data  True if the business holds proprietary datasets or IP.
        has_network_effect    True if value compounds as user base grows.
        revenue_floor         Monthly revenue threshold below which business is considered dead.
    """
    d = deal.model_copy(deep=True)

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
    # else: preserve caller-supplied value

    # value_add_score: preserve if non-zero, else default 70
    if d.value_add_score == 0.0:
        d.value_add_score = 70.0

    # buy_vs_build_score: preserve if manually set (>0), else compute from decision
    if d.buy_vs_build_score == 0.0:
        d.buy_vs_build_score = round(
            _buy_vs_build_score(d.buy_vs_build_decision, d.moat_score), 2
        )
    # else: keep the manually-provided value

    d.risk_score = round(_risk_score(d.age_years, d.category), 2)

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

    d.overall_score = _overall_score(
        d.cashflow_score,
        d.moat_score,
        d.ai_proof_score,
        d.value_add_score,
        d.risk_score,
        d.competitor_analysis_score,
        d.company_life_score,
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
