"""
EVA Deal Scout — Unified pipeline data models (pydantic v2, pure).

These models describe the DB-backed sourcing/scoring pipeline and are
deliberately free of any FastAPI / aiosqlite import so they can be exercised
by the test-suite under a bare interpreter.

Pipeline stages
---------------
    SOURCE : adapters write normalized ``RawDeal`` rows + ``DealSnapshot``
             observations into the store, one ``SourceRun`` per invocation.
    SCORE  : the scoring gate selects stored raw rows and the v6 11-param
             composite writes ``ScoredDeal`` rows.  Transient JSON is never
             scored directly — only rows already persisted in the store.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    """UTC ISO-8601 timestamp used for every created_at / updated_at field."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Enumerations (kept as plain tuples so callers can validate cheaply)
# ---------------------------------------------------------------------------

RUN_STATUSES = ("running", "completed", "failed", "seeded_not_fetchable")
MARKET_STATUSES = ("available", "sold", "off_market", "under_offer")
TRUST_LEVELS = ("high", "medium", "low")
CASE_STUDY_TYPES = ("within_box", "juggernaut_study", "build_vs_buy_reference")


class SourceRun(BaseModel):
    """One invocation of a single source adapter."""

    id: str
    source: str
    adapter: str = ""
    mode: str = "source"                    # "source" | "backfill"
    status: str = "running"                 # RUN_STATUSES
    deals_found: int = 0
    deals_new: int = 0
    deals_updated: int = 0
    snapshots_added: int = 0
    error: str = ""
    started_at: str = Field(default_factory=now_iso)
    finished_at: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RawDeal(BaseModel):
    """A normalized listing row.  Deduped by (source, dedupe_key)."""

    id: str
    source_run_id: str = ""
    source: str
    listing_id: str = ""
    url: str = ""
    dedupe_key: str = ""                     # listing_id or url — computed on upsert
    name: str = ""
    category: str = "SaaS"
    monthly_net: float = 0.0
    annual_multiple: float = 0.0
    asking_price: float = 0.0
    age_years: float = 0.0
    currency: str = "USD"

    # Geography signals used by the scoring gate
    registration_country: str = ""           # e.g. "US", "GB", "FR"
    primary_customer_market: str = ""
    seller_location: str = ""

    # Trust / vetting level inferred from the source adapter
    trust_level: str = "low"                 # TRUST_LEVELS

    # Closed / sold comp fields (populated for closed-deal ingests)
    is_closed: bool = False
    market_status: str = "available"         # MARKET_STATUSES
    sold_price: float = 0.0
    sold_at: str = ""
    owner_hours_per_week: float = 0.0

    # Pre-computed score carried in from a source payload (e.g. the unified
    # radar export).  Used to rank deals the gate skips — never overwrites the
    # DB-side v6 scorer output.
    incoming_score: float = 0.0

    # Scoring-gate audit (stamped during the SCORE stage for every open deal,
    # including those the gate skips — so skip reasons stay queryable).
    gate_status: str = "pending"             # "pending" | "scored" | "skipped"
    us_eligible: bool = False
    trust_high: bool = False
    skip_reason: str = ""

    notes: str = ""
    raw_json: str = "{}"                     # full untouched source payload

    sourced_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class DealSnapshot(BaseModel):
    """A point-in-time status observation for a raw deal."""

    id: str
    raw_deal_id: str
    source_run_id: str = ""
    market_status: str = "available"
    asking_price: float = 0.0
    monthly_net: float = 0.0
    observed_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class ScoredDeal(BaseModel):
    """Output of the v6 11-param composite for a gated raw deal."""

    id: str
    raw_deal_id: str
    source: str = ""
    listing_id: str = ""

    # Gate decision metadata
    us_eligible: bool = False
    trust_high: bool = False
    trust_level: str = "low"
    gate_reason: str = ""
    skip_reason: str = ""                     # empty for scored rows (audit symmetry)

    # v6 11-param composite dimensions
    cashflow_score: float = 0.0
    moat_score: float = 0.0
    ai_proof_score: float = 0.0
    value_add_score: float = 0.0
    buy_vs_build_score: float = 0.0
    risk_score: float = 0.0
    mitigation_score: float = 0.0
    competitor_analysis_score: float = 0.0
    company_life_score: float = 0.0
    owner_neglect_score: float = 0.0
    adobe_platform_risk_score: float = 0.0
    overall_score: float = 0.0

    # Buy-vs-Build assessment (computed for every scored deal).  The deal-killer
    # for the build path is a high ``moat_build_years``.
    build_feasibility: str = ""              # "high" | "medium" | "low"
    build_time_estimate: str = ""            # engineering calendar estimate
    moat_build_years: float = 0.0            # yrs to rebuild a defensible moat
    buy_vs_build_recommendation: str = ""    # "buy" | "build" | "either"
    buy_vs_build_rationale: str = ""

    score_json: str = "{}"                   # full analyzer dump for audit

    scored_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Competitor(BaseModel):
    """A normalized competitor entity, deduped by lowercased name.

    Competitor-level facts (what_they_do, pricing_model, category) compound on
    this shared row so researched intel is reused across every deal that links
    to the same company.  The deal-specific ``moat_comparison`` lives on the
    ``deal_competitors`` join, not here.
    """

    id: str = ""
    name: str
    what_they_do: str = ""
    pricing_model: str = ""
    url: str = ""
    category: str = ""
    source_url: str = ""
    # Present only on rows returned via ``list_competitors`` (from the join).
    moat_comparison: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class CaseStudy(BaseModel):
    """A 4-lens deal case study — Eva's compounding acquisition intelligence.

    Each row captures BOTH a ``snapshot`` of the deal (metrics + narrative) AND
    the 4-lens ``analysis`` that turns a single deal into reusable
    pattern/formula/moat intelligence, both stored as JSON blobs.  ``deal_id``
    links to a ``raw_deals`` row when the study is of an in-pipeline deal, but is
    NULLABLE for out-of-box studies (juggernauts, build-vs-buy references) that
    Eva studies without sourcing them.  Deduped (upserted) by ``source_url``.
    """

    id: str = ""
    source_url: str = ""                     # upsert key (unique)
    deal_type: str = "within_box"            # CASE_STUDY_TYPES
    title: str = ""
    deal_id: Optional[str] = None            # FK raw_deals.id, NULL for out-of-box

    # deal metrics: asking, revenue, profit, margin, multiples, founded,
    # customers, team, location, usp.
    snapshot: dict = Field(default_factory=dict)
    # the 4 lenses: lens1_box_fit, lens2_what_selling, lens3_juggernaut_arc,
    # lens4_build_vs_buy.
    analysis: dict = Field(default_factory=dict)

    pattern_tags: list[str] = Field(default_factory=list)
    formula_insight: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class BoxEvaluation(BaseModel):
    """A "deal box" hard-criteria verdict for a scored deal.

    Computed post-scoring at the current run-rate: models the intended
    seller-note + interest-only-HELOC financing, then tests free cash flow,
    DSCR, and the recent trend against the box thresholds.  ``box_pass`` marks a
    deal as an in-box (stable-base) candidate.  Upserted by ``deal_id``.
    """

    id: str = ""
    deal_id: str                              # FK raw_deals.id (the scored deal)
    asking: float = 0.0
    monthly_net_used: float = 0.0             # run-rate net (last month or ttm avg)
    seller_note_pmt: float = 0.0
    heloc_pmt: float = 0.0
    total_debt: float = 0.0
    free_cash_flow: float = 0.0
    dscr: float = 0.0
    trend_pass: bool = False
    box_pass: bool = False
    box_reason: list[str] = Field(default_factory=list)
    config_snapshot: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class TrendReport(BaseModel):
    """A saved market-trend analysis over closed vs open comps."""

    id: str
    title: str = "Deal Trend Report"
    report_md: str = ""
    stats_json: str = "{}"
    generated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)
