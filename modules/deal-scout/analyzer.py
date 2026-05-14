"""
EVA Deal Scout — Scoring & Financial Analysis Engine
=====================================================

Implements analyze_deal(deal: Deal) -> Deal, computing:
  - cashflow_score    (0–100)
  - moat_score        (0–100)
  - ai_proof_score    (0–100)  [can be pre-set by user]
  - value_add_score   (0–100)  [manual / preserved if already set]
  - buy_vs_build_score (0–10)
  - risk_score        (0–100)
  - overall_score     (0–10, weighted composite)

  Financial fields:
  - down_payment            20% of asking_price
  - seller_finance_amount   80% of asking_price
  - monthly_debt_service    PMT(7% / 12, 60 periods, seller_finance_amount)
  - net_monthly_cashflow    monthly_net - monthly_debt_service
  - heloc_used              == down_payment
  - heloc_interest_monthly  heloc_used * 0.095 / 12
  - net_after_heloc         net_monthly_cashflow - heloc_interest_monthly
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


def _moat_score(age_years: float, category: str) -> float:
    """Age bracket base + category bonus."""
    if age_years < 5:
        base = 40.0
    elif age_years < 10:
        base = 70.0
    else:
        base = 90.0

    bonus = CATEGORY_MOAT_BONUS.get(category, 0.0)
    return _clamp(base + bonus)


def _ai_proof_score(age_years: float, category: str, current_score: float) -> float:
    """Category baseline + age trust bonus (+5 if age >= 5 years).
    
    If the caller has already set a non-zero score, preserve it (only apply
    the age adjustment if the score was auto-computed, i.e. == 0 at call time).
    We distinguish by checking whether it equals the raw baseline — but to keep
    it simple we always recompute so the rules are deterministic; callers that
    want to lock a value should pass it via the model and skip re-scoring.
    """
    base = CATEGORY_AI_PROOF_BASE.get(category, 70.0)
    age_bonus = 5.0 if age_years >= 5 else 0.0
    return _clamp(base + age_bonus)


def _risk_score(age_years: float, category: str) -> float:
    """min(age_years * 8, 90) - 20 if Digital Products."""
    base = min(age_years * 8.0, 90.0)
    penalty = CATEGORY_RISK_PENALTY.get(category, 0.0)
    return _clamp(base + penalty)


def _overall_score(
    cashflow: float,
    moat: float,
    ai_proof: float,
    value_add: float,
    risk: float,
) -> float:
    """Weighted composite on 0–100 scale, then normalised to 0–10.

    Weights: cashflow 25%, moat 20%, ai_proof 25%, value_add 15%, risk 15%
    """
    composite = (
        cashflow * 0.25
        + moat * 0.20
        + ai_proof * 0.25
        + value_add * 0.15
        + risk * 0.15
    )
    # Normalise 0–100 → 0–10
    return round(_clamp(composite / 10.0, 0.0, 10.0), 2)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_deal(deal: Deal) -> Deal:
    """Compute all scores and financial fields; return an updated Deal copy."""
    d = deal.model_copy(deep=True)

    # ---- scoring ----
    d.cashflow_score = round(_cashflow_score(d.monthly_net), 2)
    d.moat_score = round(_moat_score(d.age_years, d.category), 2)

    # ai_proof_score: use provided value if non-zero, else compute
    if d.ai_proof_score == 0.0:
        d.ai_proof_score = round(_ai_proof_score(d.age_years, d.category, d.ai_proof_score), 2)
    # else: preserve caller-supplied value

    # value_add_score: preserve if non-zero, else default 70
    if d.value_add_score == 0.0:
        d.value_add_score = 70.0

    d.buy_vs_build_score = round(d.moat_score / 10.0, 1)
    d.risk_score = round(_risk_score(d.age_years, d.category), 2)

    d.overall_score = _overall_score(
        d.cashflow_score,
        d.moat_score,
        d.ai_proof_score,
        d.value_add_score,
        d.risk_score,
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
