"""
EVA Deal Analyzer Agent — Pydantic models (v7)
==============================================

Extends the deal-scout v6 `Deal` model with v7 scoring fields. The base model is
loaded directly from modules/deal-scout/models.py by file path (aliased so the
two flat "models" modules do not collide on sys.path), then subclassed — every
v6 field is inherited and preserved.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Load the deal-scout base Deal model by file path (aliased to avoid name clash)
# ---------------------------------------------------------------------------

_BASE_MODELS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "deal-scout", "models.py")
)
_spec = importlib.util.spec_from_file_location("deal_scout_models", _BASE_MODELS_PATH)
_deal_scout_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_deal_scout_models)

Deal = _deal_scout_models.Deal                       # v6 base
VALID_STAGES = _deal_scout_models.VALID_STAGES
VALID_BUY_VS_BUILD = _deal_scout_models.VALID_BUY_VS_BUILD
VALID_MARKET_STATUS = _deal_scout_models.VALID_MARKET_STATUS

# v7 canonical taxonomy (kept in sync with scoring_v7.V2_CATEGORIES).
VALID_CATEGORIES_V2 = [
    "SaaS",
    "Software/Digital",
    "Services",
    "Content/Media",
    "Education/Info",
    "Physical Ecommerce",
    "Legacy/Needs Review",
]

VALID_RESEARCH_LEVELS = ["L0", "L1", "L2"]


class DealV7(Deal):
    """v6 Deal + v7 scoring dimensions. All v6 fields are inherited unchanged."""

    # Taxonomy split
    category_v2: str = ""                        # derived from legacy `category` + hints

    # New v7 scoring dimensions
    exit_potential_score: float = 0.0            # 0-100 category multiple ceiling + headroom
    profit_potential_score: float = 0.0          # 0-100 composite (replaces value_add_score)
    profit_lever_scores: dict = {}               # per-lever breakdown for profit_potential
    tam_score: float = 0.0                        # 0-100 market attractiveness (0 if TAM absent)

    # Enriched TAM inputs
    tam_usd: float = 0.0
    sam_usd: float = 0.0
    market_growth_rate_pct: float = 0.0
    tam_confidence: float = 0.0                   # 0-100 confidence in the TAM figure

    # Tiered competitor analysis
    research_level: str = "L0"                    # "L0" | "L1" | "L2"
    named_competitors: list = []                  # L1 field
    estimated_market_share: Optional[float] = None  # L1 field (subject's own share, 0-100)
    niche_growth_score: Optional[float] = None    # L0 niche-dynamics input (0-100)
    market_fragmentation_score: Optional[float] = None  # L0 niche-dynamics input (0-100)

    # Generalised platform risk (renamed from v6 adobe_platform_risk_score)
    platform_dependency_risk_score: float = 0.0   # 0-100, higher = more platform risk

    # Bookkeeping
    scoring_version: str = "7.0.0"


class Enrichment(BaseModel):
    """Optional enrichment payload accepted by analyze_deal_v7 / POST /analyze.

    Every field is optional. Absent fields cause the engine to score what it can
    and flag the gap (e.g. no tam_usd -> tam_score 0; no named_competitors -> L0).
    """
    # TAM
    tam_usd: Optional[float] = None
    sam_usd: Optional[float] = None
    market_growth_rate_pct: Optional[float] = None
    tam_source_url: Optional[str] = None
    tam_confidence_score: Optional[float] = None

    # Competitor (L0 niche dynamics + L1 research)
    num_competitors: Optional[int] = None
    niche_growth_score: Optional[float] = None
    market_fragmentation_score: Optional[float] = None
    named_competitors: Optional[list] = None
    estimated_market_share: Optional[float] = None

    # Structural moat / risk knobs
    has_sdk_integration: Optional[bool] = None
    has_proprietary_data: Optional[bool] = None
    has_network_effect: Optional[bool] = None
    single_owner_dependent: Optional[bool] = None
    financing_required: Optional[bool] = None
    peak_monthly_net: Optional[float] = None
    owner_neglect_months: Optional[int] = None
    owner_is_sole_operator: Optional[bool] = None

    # Platform dependency
    platform_name: Optional[str] = None
    platform_native_overlap_pct: Optional[float] = None

    # Growth levers: {lever_name: {current_utilization, addable_upside,
    #                              feasibility, evidence_confidence}}
    growth_levers: Optional[dict] = None

    def to_kwargs(self) -> dict:
        """Return a dict of only the set fields, suitable for analyze_deal_v7(enrichment=...)."""
        return self.model_dump(exclude_none=True)


class KnownOutcome(BaseModel):
    """Optional label for a CLOSED deal fed through the cascade for training.

    Closed-deal scouting (sourcing already-sold listings) is a SEPARATE follow-up
    microservice; this model is the seam so the cascade + learning records can
    accept a known outcome now — it flows into training_observations and, later,
    learn.recalibrate() with a real result to calibrate against.
    """
    sale_price: Optional[float] = None
    final_multiple: Optional[float] = None
    time_to_close_days: Optional[int] = None

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


class AnalyzeRequest(BaseModel):
    """POST /analyze payload: a deal (as DealCreate-style fields) + optional enrichment."""
    # Core deal fields (mirrors deal-scout DealCreate essentials)
    name: str
    category: str = "SaaS"
    monthly_net: float
    annual_multiple: float
    asking_price: float
    age_years: float
    source: str = "manual"
    listing_id: str = ""
    url: str = ""
    notes: str = ""
    buy_vs_build_decision: str = "buy"
    ai_proof_score: Optional[float] = None

    enrichment: Optional[Enrichment] = None


class AgentHealth(BaseModel):
    status: str
    module: str
    version: str
    scoring_version: str
    db: str
    directive_version: str
