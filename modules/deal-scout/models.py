"""
EVA Deal Scout — Pydantic models
Module 3 of the EVA digital acquisition intelligence system.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Deal(BaseModel):
    id: str                          # UUID
    source: str                      # "flippa" | "empire_flippers" | "acquire" | "manual"
    listing_id: str
    url: str
    name: str
    category: str                    # "SaaS" | "Content" | "Services" | "Education" | "Digital Products"
    monthly_net: float               # monthly net profit ($)
    annual_multiple: float           # normalized annual multiple (EF: divide raw by 12)
    asking_price: float
    age_years: float
    status: str                      # "tracking" | "nda_requested" | "under_review" | "passed" | "pursuing"
    notes: str = ""

    # Scoring dimensions (0–100 each; overall 0–10)
    cashflow_score: float = 0.0
    moat_score: float = 0.0          # difficulty to replicate
    ai_proof_score: float = 0.0      # runway before AI disruption
    value_add_score: float = 0.0     # upside buyer can add
    buy_vs_build_score: float = 0.0  # 0–10
    risk_score: float = 0.0          # higher = safer
    overall_score: float = 0.0       # weighted composite 0–10

    # Financial analysis
    down_payment: float = 0.0              # 20% of asking_price
    seller_finance_amount: float = 0.0     # 80% of asking_price
    monthly_debt_service: float = 0.0      # PMT at 7% / 60 months
    net_monthly_cashflow: float = 0.0      # monthly_net - debt_service
    heloc_used: float = 0.0                # == down_payment (funded via HELOC @ 9.5%)
    heloc_interest_monthly: float = 0.0    # heloc_used * 0.095 / 12
    net_after_heloc: float = 0.0           # net_monthly_cashflow - heloc_interest_monthly

    created_at: str
    updated_at: str


class DealCreate(BaseModel):
    """Payload accepted by POST /deals (all score/financial fields are optional overrides)."""
    source: str = "manual"
    listing_id: str = ""
    url: str = ""
    name: str
    category: str = "SaaS"
    monthly_net: float
    annual_multiple: float
    asking_price: float
    age_years: float
    status: str = "tracking"
    notes: str = ""

    # Optional manual overrides for scoring dimensions
    cashflow_score: Optional[float] = None
    moat_score: Optional[float] = None
    ai_proof_score: Optional[float] = None
    value_add_score: Optional[float] = None
    buy_vs_build_score: Optional[float] = None
    risk_score: Optional[float] = None
    overall_score: Optional[float] = None


class DealUpdate(BaseModel):
    """Payload accepted by PUT /deals/{id} — all fields optional."""
    source: Optional[str] = None
    listing_id: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    monthly_net: Optional[float] = None
    annual_multiple: Optional[float] = None
    asking_price: Optional[float] = None
    age_years: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    cashflow_score: Optional[float] = None
    moat_score: Optional[float] = None
    ai_proof_score: Optional[float] = None
    value_add_score: Optional[float] = None
    buy_vs_build_score: Optional[float] = None
    risk_score: Optional[float] = None
    overall_score: Optional[float] = None


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
