"""
EVA Deal Financing Agent — Pydantic models
===========================================

Bottoms-up real-estate / small-business acquisition financing model.
Every output number is DERIVED from inputs via the engine (financing_engine.py) —
never a hardcoded or assumed top-down yield. See directive.md "No-Circularity Rule".
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RevenueAssumptions(BaseModel):
    """Bottoms-up revenue build. If bed-level detail is available, use it;
    otherwise fall back to actual/projected total revenue from the P&L."""
    annual_revenue: float = Field(..., description="Actual or projected total annual revenue ($)")
    year_label: str = Field("", description="e.g. '2025 actual', '2026 projection'")
    revenue_growth_pct: float = Field(0.0, description="YoY growth rate applied for hold-period projection")


class OperatingExpenses(BaseModel):
    """Operating expense build, excluding debt service and depreciation (those are
    applied separately downstream — never blended into NOI)."""
    annual_opex: float = Field(..., description="Total annual operating expenses excluding debt service ($)")
    opex_growth_pct: float = Field(0.0, description="YoY opex growth rate (e.g. inflation) for projection")


class FinancingTerms(BaseModel):
    """Acquisition financing structure. Debt service is calculated bottoms-up
    from these terms via standard amortization — never assumed."""
    purchase_price: float
    working_capital: float = 0.0
    closing_costs: float = 0.0
    loan_amount: float
    equity_injection: float
    annual_interest_rate_pct: float = Field(
        ..., description="Loan rate, e.g. SBA 7(a) real-estate rate. Must be explicit, never omitted."
    )
    amortization_years: int = Field(25, description="Loan amortization term in years")
    seller_note_amount: float = 0.0
    seller_note_rate_pct: float = 0.0
    seller_note_years: int = 0
    rate_source_note: str = Field(
        "", description="Provenance for the rate assumption (market data + date), for audit trail"
    )

    @property
    def total_project_cost(self) -> float:
        return self.purchase_price + self.working_capital + self.closing_costs


class DealFinancingInput(BaseModel):
    deal_name: str
    property_type: str = "RCFE"
    beds: Optional[int] = None
    revenue: RevenueAssumptions
    opex: OperatingExpenses
    financing: FinancingTerms
    hold_period_years: int = 5
    exit_cap_rate_pct: Optional[float] = Field(
        None, description="If set, models a sale at exit using NOI(exit_year)/cap_rate. If omitted, exit value is not modeled."
    )
    source_notes: str = ""


class YearCashFlow(BaseModel):
    year: int
    revenue: float
    opex: float
    noi: float
    debt_service_senior: float
    debt_service_seller_note: float
    total_debt_service: float
    cash_flow_to_equity: float
    dscr: float  # Debt Service Coverage Ratio = NOI / total_debt_service


class DealFinancingResult(BaseModel):
    deal_name: str
    total_project_cost: float
    loan_amount: float
    equity_injection: float
    loan_to_cost_pct: float
    annual_interest_rate_pct: float
    amortization_years: int
    monthly_debt_service_senior: float
    annual_debt_service_senior: float
    year1_noi: float
    year1_dscr: float
    year1_cash_flow_to_equity: float
    year1_cash_on_cash_pct: float
    yearly: list[YearCashFlow]
    exit_value: Optional[float] = None
    net_sale_proceeds: Optional[float] = None
    equity_multiple: Optional[float] = None
    irr_pct: Optional[float] = None
    flags: list[str] = []
    rate_source_note: str = ""
    computed_at: str = ""


class AgentHealth(BaseModel):
    status: str
    module: str
    version: str
    directive_version: str
