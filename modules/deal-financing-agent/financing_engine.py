"""
EVA Deal Financing Agent — deterministic bottoms-up financing engine
=====================================================================

NO-CIRCULARITY RULE (see directive.md): every downstream number is derived
step-by-step from primary inputs (revenue, opex, loan terms). We NEVER assume
a target yield/IRR and back-solve into cash flow, and we NEVER let debt
service be a plug that forces a chosen return. The chain is strictly:

    revenue, opex  ->  NOI
    loan terms     ->  amortized debt service (standard mortgage formula)
    NOI, debt svc  ->  cash flow to equity, DSCR
    cash flows,
    equity, exit   ->  cash-on-cash, equity multiple, IRR (computed from the
                       resulting cash flow stream, not assumed)

Pure functions. No I/O, no LLM calls — fully unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from models import (
    DealFinancingInput,
    DealFinancingResult,
    YearCashFlow,
)

ENGINE_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Amortization primitives
# ---------------------------------------------------------------------------

def monthly_payment(principal: float, annual_rate_pct: float, amort_years: int) -> float:
    """Standard fixed-rate amortizing mortgage payment. Returns 0 if principal <= 0."""
    if principal <= 0 or amort_years <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    n = amort_years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def remaining_balance(principal: float, annual_rate_pct: float, amort_years: int, years_elapsed: float) -> float:
    """Outstanding principal balance after `years_elapsed` years of on-schedule
    monthly payments on a fixed-rate amortizing loan."""
    if principal <= 0 or amort_years <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    n = amort_years * 12
    m = min(int(round(years_elapsed * 12)), n)
    if r == 0:
        return max(principal - principal / n * m, 0.0)
    pmt = monthly_payment(principal, annual_rate_pct, amort_years)
    bal = principal * (1 + r) ** m - pmt * (((1 + r) ** m - 1) / r)
    return max(bal, 0.0)


# ---------------------------------------------------------------------------
# IRR (bisection — avoids a numpy-financial dependency)
# ---------------------------------------------------------------------------

def _npv(rate: float, cashflows: List[float]) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows: List[float], lo: float = -0.99, hi: float = 10.0, tol: float = 1e-6, max_iter: int = 200) -> Optional[float]:
    """Bisection IRR solver. cashflows[0] is t=0 (typically negative, the equity
    outlay). Returns None if no sign change / no solution found in [lo, hi]."""
    f_lo, f_hi = _npv(lo, cashflows), _npv(hi, cashflows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # no sign change in bracket -> no real IRR found here
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def build_yearly_cashflows(inp: DealFinancingInput) -> List[YearCashFlow]:
    fin = inp.financing
    senior_annual_ds = monthly_payment(fin.loan_amount, fin.annual_interest_rate_pct, fin.amortization_years) * 12
    seller_annual_ds = 0.0
    if fin.seller_note_amount > 0 and fin.seller_note_years > 0:
        seller_annual_ds = monthly_payment(fin.seller_note_amount, fin.seller_note_rate_pct, fin.seller_note_years) * 12

    rev0 = inp.revenue.annual_revenue
    opex0 = inp.opex.annual_opex
    g_rev = inp.revenue.revenue_growth_pct / 100.0
    g_opex = inp.opex.opex_growth_pct / 100.0

    yearly: List[YearCashFlow] = []
    for y in range(1, inp.hold_period_years + 1):
        revenue_y = rev0 * ((1 + g_rev) ** (y - 1))
        opex_y = opex0 * ((1 + g_opex) ** (y - 1))
        noi_y = revenue_y - opex_y
        total_ds = senior_annual_ds + seller_annual_ds
        cfe = noi_y - total_ds
        dscr = (noi_y / total_ds) if total_ds > 0 else float("inf")
        yearly.append(
            YearCashFlow(
                year=y,
                revenue=round(revenue_y, 2),
                opex=round(opex_y, 2),
                noi=round(noi_y, 2),
                debt_service_senior=round(senior_annual_ds, 2),
                debt_service_seller_note=round(seller_annual_ds, 2),
                total_debt_service=round(total_ds, 2),
                cash_flow_to_equity=round(cfe, 2),
                dscr=round(dscr, 2) if dscr != float("inf") else 9999.0,
            )
        )
    return yearly


def run_financing_model(inp: DealFinancingInput) -> DealFinancingResult:
    fin = inp.financing
    yearly = build_yearly_cashflows(inp)
    flags: List[str] = []

    senior_monthly = monthly_payment(fin.loan_amount, fin.annual_interest_rate_pct, fin.amortization_years)
    senior_annual = senior_monthly * 12

    y1 = yearly[0]
    cash_on_cash_1 = (y1.cash_flow_to_equity / fin.equity_injection * 100.0) if fin.equity_injection > 0 else None

    if y1.dscr < 1.25 and y1.dscr != 9999.0:
        flags.append(
            f"Year-1 DSCR {y1.dscr:.2f}x is below the typical SBA lender minimum of 1.25x — "
            "this deal may not qualify as underwritten."
        )
    if fin.annual_interest_rate_pct <= 0:
        flags.append("No interest rate provided — debt service cannot be computed. Provide actual lender term sheet rate.")

    exit_value = None
    net_sale_proceeds = None
    equity_multiple = None
    irr_pct = None

    if inp.exit_cap_rate_pct and inp.exit_cap_rate_pct > 0:
        exit_year_noi = yearly[-1].noi
        exit_value = exit_year_noi / (inp.exit_cap_rate_pct / 100.0)
        remaining_senior = remaining_balance(fin.loan_amount, fin.annual_interest_rate_pct, fin.amortization_years, inp.hold_period_years)
        remaining_seller = remaining_balance(fin.seller_note_amount, fin.seller_note_rate_pct, fin.seller_note_years, inp.hold_period_years) if fin.seller_note_amount > 0 else 0.0
        net_sale_proceeds = exit_value - remaining_senior - remaining_seller

        cashflow_stream = [-fin.equity_injection]
        for i, yr in enumerate(yearly):
            cf = yr.cash_flow_to_equity
            if i == len(yearly) - 1:
                cf += net_sale_proceeds
            cashflow_stream.append(cf)

        total_returned = sum(yr.cash_flow_to_equity for yr in yearly) + net_sale_proceeds
        equity_multiple = round(total_returned / fin.equity_injection, 2) if fin.equity_injection > 0 else None
        r = irr(cashflow_stream)
        irr_pct = round(r * 100.0, 2) if r is not None else None
        if irr_pct is None:
            flags.append("IRR did not converge for the given cash-flow stream (check inputs for sign issues).")
    else:
        flags.append("No exit cap rate provided — exit value, equity multiple, and IRR are not modeled (hold-only cash flow analysis).")

    return DealFinancingResult(
        deal_name=inp.deal_name,
        total_project_cost=round(fin.total_project_cost, 2),
        loan_amount=round(fin.loan_amount, 2),
        equity_injection=round(fin.equity_injection, 2),
        loan_to_cost_pct=round(fin.loan_amount / fin.total_project_cost * 100.0, 2) if fin.total_project_cost > 0 else 0.0,
        annual_interest_rate_pct=fin.annual_interest_rate_pct,
        amortization_years=fin.amortization_years,
        monthly_debt_service_senior=round(senior_monthly, 2),
        annual_debt_service_senior=round(senior_annual, 2),
        year1_noi=y1.noi,
        year1_dscr=y1.dscr,
        year1_cash_flow_to_equity=y1.cash_flow_to_equity,
        year1_cash_on_cash_pct=round(cash_on_cash_1, 2) if cash_on_cash_1 is not None else 0.0,
        yearly=yearly,
        exit_value=round(exit_value, 2) if exit_value is not None else None,
        net_sale_proceeds=round(net_sale_proceeds, 2) if net_sale_proceeds is not None else None,
        equity_multiple=equity_multiple,
        irr_pct=irr_pct,
        flags=flags,
        rate_source_note=fin.rate_source_note,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
