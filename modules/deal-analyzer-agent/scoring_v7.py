"""
EVA Deal Analyzer Agent — Scoring Core (v7)
===========================================

Pure, deterministic scoring engine. NO network, NO LLM, NO I/O.
Successor to deal-scout/analyzer.py (v6). The whole point of separating this
from agent.py is that the engine is fully testable offline — see test_v7.py.

WHAT CHANGED FROM v6
--------------------
1. TAXONOMY SPLIT — the vague legacy "Digital Products" bucket is split into:
     - "Software/Digital"   (higher multiples, higher AI-proof, low platform risk)
     - "Physical Ecommerce" (lower multiples, high platform/inventory risk)
   A `category_v2` field is derived via migrate_category(); all CATEGORY_*
   constant dicts are defined over the v2 taxonomy.

2. THREE NEW DIMENSIONS
     - exit_potential_score   (0-100) category revenue-multiple ceiling + headroom
     - profit_potential_score (0-100) composite of ~12 growth levers
                              (replaces the vague v6 value_add_score)
     - tam_score              (0-100) market size / growth / penetration headroom

3. TIERED COMPETITOR ANALYSIS — competitor_analysis_score now accepts optional
   L1 research fields (named_competitors, estimated_market_share, niche_growth,
   fragmentation) and reports a research_level.

4. GENERALISED PLATFORM RISK — adobe_platform_risk_score is renamed to
   platform_dependency_risk_score. Adobe is now just one instance.

5. REWEIGHTED COMPOSITE — 13 weighted axes summing to 1.0 (see _overall_score).

6. GENERIC RATIONALES — no hardcoded case-study commentary. The batch.ai
   narrative that lived in v6 now lives in cases/batch_ai.md.

Entry point: analyze_deal_v7(deal, enrichment=None, **kwargs) -> DealV7
Backward compatible: if enrichment / v7 kwargs are absent, it scores what it
can and flags the gaps (tam_score returns 0, competitor stays at L0, etc.).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from models import DealV7


# ===========================================================================
# v2 TAXONOMY
# ===========================================================================

V2_CATEGORIES = [
    "SaaS",
    "Software/Digital",
    "Services",
    "Content/Media",
    "Education/Info",
    "Physical Ecommerce",
    "Legacy/Needs Review",
]

# Keyword signals used to disambiguate the legacy "Digital Products" bucket.
_PHYSICAL_SIGNALS = (
    "fba", "amazon", "shopify", "inventory", "ecommerce", "e-commerce",
    "dropship", "physical", "warehouse", "sku", "supplier", "wholesale",
)
_SOFTWARE_SIGNALS = (
    "app", "plugin", "software", "extension", "api", "digital tool",
    "chrome extension", "mobile app", "desktop app", "template", "download",
)

# Direct legacy -> v2 map for the unambiguous v6 categories.
_LEGACY_DIRECT_MAP = {
    "saas": "SaaS",
    "services": "Services",
    "education": "Education/Info",
    "content": "Content/Media",
}


def migrate_category(legacy_category: str, hint: str = "") -> str:
    """Map a legacy v6 category (+ optional free-text hint) to a v2 category.

    Rules (per the v7 taxonomy directive):
      - Amazon FBA / Shopify / inventory / physical  -> "Physical Ecommerce"
      - SaaS / software / app / plugin               -> "SaaS" or "Software/Digital"
      - unambiguous legacy cats                       -> direct map
      - ambiguous (e.g. bare "Digital Products")      -> "Legacy/Needs Review"

    `hint` should be the deal name + notes so keyword signals can disambiguate.
    """
    if not legacy_category:
        return "Legacy/Needs Review"

    # Already a v2 category — pass through.
    if legacy_category in V2_CATEGORIES:
        return legacy_category

    key = legacy_category.strip().lower()
    text = f"{legacy_category} {hint}".lower()

    # Unambiguous legacy categories map directly (SaaS wins even if hint says "app").
    if key in _LEGACY_DIRECT_MAP:
        return _LEGACY_DIRECT_MAP[key]

    # Ambiguous "Digital Products" and anything unknown: disambiguate by signal.
    if any(sig in text for sig in _PHYSICAL_SIGNALS):
        return "Physical Ecommerce"
    if any(sig in text for sig in _SOFTWARE_SIGNALS):
        return "Software/Digital"

    return "Legacy/Needs Review"


# ===========================================================================
# CATEGORY CONSTANTS (defined over the v2 taxonomy)
# ===========================================================================

CATEGORY_MOAT_BONUS: dict[str, float] = {
    "Services": 15.0,
    "Education/Info": 10.0,
    "SaaS": 5.0,
    "Software/Digital": 3.0,
    "Content/Media": 0.0,
    "Physical Ecommerce": -12.0,   # platform + commodity supply = weak structural moat
    "Legacy/Needs Review": 0.0,
}

CATEGORY_AI_PROOF_BASE: dict[str, float] = {
    "Services": 85.0,
    "Education/Info": 80.0,
    "SaaS": 75.0,
    "Software/Digital": 68.0,      # higher than physical: real product IP survives AI
    "Content/Media": 60.0,
    "Physical Ecommerce": 55.0,    # goods are AI-resistant, but discovery is not
    "Legacy/Needs Review": 60.0,
}

CATEGORY_COMPETITOR_BASE: dict[str, float] = {
    "Services": 60.0,
    "Education/Info": 55.0,
    "SaaS": 50.0,
    "Software/Digital": 45.0,
    "Content/Media": 40.0,
    "Physical Ecommerce": 35.0,
    "Legacy/Needs Review": 45.0,
}

# Monthly revenue decay rate if left untouched (no marketing/ops effort).
CATEGORY_DECAY_RATE: dict[str, float] = {
    "SaaS": 0.04,
    "Software/Digital": 0.05,
    "Services": 0.06,
    "Education/Info": 0.03,
    "Content/Media": 0.07,
    "Physical Ecommerce": 0.08,
    "Legacy/Needs Review": 0.06,
}

# Base risk exposure by category (0-100, higher = riskier).
CATEGORY_BASE_RISK: dict[str, float] = {
    "SaaS": 35.0,
    "Software/Digital": 42.0,
    "Services": 40.0,
    "Education/Info": 30.0,
    "Content/Media": 55.0,
    "Physical Ecommerce": 60.0,    # inventory + platform + logistics
    "Legacy/Needs Review": 55.0,
}

# Base mitigation potential by category (0-100, higher = easier to offset risk).
CATEGORY_BASE_MITIGATION: dict[str, float] = {
    "SaaS": 70.0,
    "Software/Digital": 62.0,
    "Services": 60.0,
    "Education/Info": 72.0,
    "Content/Media": 50.0,
    "Physical Ecommerce": 45.0,
    "Legacy/Needs Review": 50.0,
}

# Category-level platform dependency baseline (0-100, higher = more exposed).
# Physical ecommerce lives on Amazon/Shopify; content lives on Google/social.
CATEGORY_PLATFORM_RISK_BASE: dict[str, float] = {
    "SaaS": 15.0,
    "Software/Digital": 25.0,      # app stores / host-app SDKs
    "Services": 10.0,
    "Education/Info": 20.0,
    "Content/Media": 45.0,         # SEO / algorithm dependency
    "Physical Ecommerce": 60.0,    # marketplace policy + account-suspension risk
    "Legacy/Needs Review": 30.0,
}

# Exit multiple benchmark ranges (annual earnings multiple: low, high).
CATEGORY_EXIT_MULTIPLE_RANGE: dict[str, tuple[float, float]] = {
    "SaaS": (5.0, 8.0),
    "Software/Digital": (4.0, 7.0),
    "Services": (2.0, 4.0),
    "Content/Media": (2.0, 3.0),
    "Physical Ecommerce": (2.0, 3.0),
    "Education/Info": (3.0, 5.0),
    "Legacy/Needs Review": (2.0, 4.0),
}

_MAX_EXIT_HIGH = 8.0  # SaaS ceiling — used to normalise the ceiling component.


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ===========================================================================
# FINANCIAL PRIMITIVE — PMT (preserved from v6)
# ===========================================================================

def _pmt(annual_rate: float, n_periods: int, principal: float) -> float:
    """Periodic payment for a fixed-rate amortising loan (positive amount)."""
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / n_periods
    return principal * (r * (1 + r) ** n_periods) / ((1 + r) ** n_periods - 1)


# ===========================================================================
# PRESERVED v6 SCORING AXES (retuned for v2 categories)
# ===========================================================================

def _cashflow_score(monthly_net: float) -> float:
    """(monthly_net / 15000) * 100, capped at 100."""
    return _clamp((monthly_net / 15_000.0) * 100.0)


def _moat_score(
    age_years: float,
    category_v2: str,
    num_competitors: int = 10,
    has_sdk_integration: bool = False,
    has_proprietary_data: bool = False,
    has_network_effect: bool = False,
) -> float:
    """Defensibility depth: age bracket + category bonus + structural bonuses."""
    if age_years < 5:
        base = 40.0
    elif age_years < 10:
        base = 70.0
    else:
        base = 90.0

    bonus = CATEGORY_MOAT_BONUS.get(category_v2, 0.0)
    sdk_bonus = 15.0 if has_sdk_integration else 0.0
    data_bonus = 10.0 if has_proprietary_data else 0.0
    network_bonus = 12.0 if has_network_effect else 0.0
    competitor_bonus = 10.0 if num_competitors < 5 else 0.0
    return _clamp(base + bonus + sdk_bonus + data_bonus + network_bonus + competitor_bonus)


def _ai_proof_score(age_years: float, category_v2: str) -> float:
    """Category baseline + age trust bonus (+5 if age >= 5 years)."""
    base = CATEGORY_AI_PROOF_BASE.get(category_v2, 70.0)
    age_bonus = 5.0 if age_years >= 5 else 0.0
    return _clamp(base + age_bonus)


def _risk_score(
    age_years: float,
    category_v2: str,
    monthly_net: float,
    peak_monthly_net: float,
    num_competitors: int,
    has_sdk_integration: bool,
    single_owner_dependent: bool = False,
    financing_required: bool = True,
) -> tuple[float, list]:
    """Multi-factor risk exposure (0-100, HIGHER = MORE RISK). Returns (score, flags)."""
    flags: list[str] = []
    base = CATEGORY_BASE_RISK.get(category_v2, 45.0)

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
    category_v2: str,
    moat_score: float,
    has_sdk_integration: bool,
    has_proprietary_data: bool,
    monthly_net: float,
    peak_monthly_net: float,
    age_years: float,
    num_competitors: int,
) -> tuple[float, list]:
    """How well identified risks can be offset (0-100, HIGHER = BETTER). Returns (score, actions)."""
    actions: list[str] = []
    base = CATEGORY_BASE_MITIGATION.get(category_v2, 55.0)

    if moat_score > 60:
        base += 15.0
        actions.append("Leverage structural moat as competitive barrier in positioning")

    if has_sdk_integration:
        base += 10.0
        actions.append("Protect platform/SDK integration as switching-cost moat; secure transfer terms")

    if has_proprietary_data:
        base += 8.0
        actions.append("Lock proprietary datasets into exclusive licensing before close")

    if peak_monthly_net > 0 and monthly_net < peak_monthly_net * 0.85:
        base += 12.0
        actions.append("Revenue dip is recoverable — reactivate marketing channels within 30 days")

    if age_years >= 3:
        base += 8.0
        actions.append("Established ops playbook exists — request full SOP documentation in DD")

    if num_competitors <= 5:
        base += 10.0
        actions.append("Tight niche — pricing power supports a 10-20% post-acquisition raise")

    return _clamp(base), actions


def _company_life(
    monthly_net: float,
    category_v2: str,
    moat_score: float,
    revenue_floor: float = 500.0,
) -> tuple[float, float, str]:
    """Survival runway if left untouched. Returns (months, score, label)."""
    base_decay = CATEGORY_DECAY_RATE.get(category_v2, 0.05)
    moat_dampener = moat_score / 200.0          # 0.0 - 0.5
    effective_decay = base_decay * (1.0 - moat_dampener)

    if effective_decay <= 0 or monthly_net <= revenue_floor:
        months = 0.0
    else:
        months = math.log(revenue_floor / monthly_net) / math.log(1.0 - effective_decay)
        months = max(0.0, months)

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
    """Derive buy_vs_build_score (0-10) from decision + moat depth."""
    if decision == "buy":
        return max(moat_score / 10.0, 7.0)
    elif decision == "build":
        return max(10.0 - moat_score / 10.0, 3.0)
    return 5.0  # hybrid


def _owner_neglect_score(
    monthly_net: float,
    peak_monthly_net: float,
    owner_neglect_months: int = 0,
    owner_is_sole_operator: bool = False,
) -> tuple[float, str]:
    """Damage from operator absence (0-100, HIGHER = more damage). Returns (score, rationale)."""
    _peak = peak_monthly_net if peak_monthly_net > 0 else monthly_net

    if _peak > 0 and monthly_net < _peak:
        decline_pct = (1.0 - monthly_net / _peak) * 100.0
        base = _clamp(decline_pct * 1.2)
    else:
        base = 0.0

    if owner_neglect_months > 3:
        base += min((owner_neglect_months - 3) * 3.0, 20.0)

    if owner_is_sole_operator:
        base += 15.0

    score = _clamp(base)
    decline_display = round((1.0 - monthly_net / _peak) * 100.0) if _peak > 0 else 0

    rationale = (
        f"Owner absent ~{owner_neglect_months} months; revenue moved "
        f"${_peak:,.0f} -> ${monthly_net:,.0f}/mo ({decline_display}% change). "
        + (
            "Damage concentrated in marketing/attention neglect — recovery thesis is "
            "credible within 60-90 days of active ownership."
            if score < 60 else
            "Significant neglect damage — recovery requires a structured 90-day sprint "
            "(channel reactivation, support SLA, retention)."
        )
    )
    return round(score, 2), rationale


def _platform_dependency_risk_score(
    category_v2: str,
    has_sdk_integration: bool,
    platform_native_overlap_pct: float = 0.0,
    platform_name: str = "the host platform",
) -> tuple[float, str]:
    """Risk that the host platform (Amazon, Shopify, Adobe, Google, an app store, ...)
    erodes the business via a native feature, policy change, or de-ranking.

    Generalised successor to v6's adobe_platform_risk_score (0-100, HIGHER = more risk).
    Returns (score, rationale).
    """
    base = CATEGORY_PLATFORM_RISK_BASE.get(category_v2, 30.0)

    # Native feature overlap is the sharpest form of platform risk.
    base += platform_native_overlap_pct * 40.0

    # An SDK/integration lock-in cuts both ways: it is a dependency, but it is also
    # an orchestration layer the platform cannot trivially absorb — net mitigating.
    if has_sdk_integration:
        base -= 15.0
    else:
        base += 8.0

    score = _clamp(base)
    overlap_display = round(platform_native_overlap_pct * 100)

    rationale = (
        f"Platform dependency on {platform_name}: category baseline "
        f"{CATEGORY_PLATFORM_RISK_BASE.get(category_v2, 30.0):.0f}/100, native feature "
        f"overlap ~{overlap_display}%. "
        + (
            "Dependency is manageable — diversify channels/integrations to reduce single-platform exposure."
            if score < 40 else
            "Elevated platform risk — multi-platform diversification is the critical "
            "risk-reduction lever; execute within 6 months of acquisition."
        )
    )
    return round(score, 2), rationale


def _breakeven_with_draw(
    down_payment: float,
    monthly_net: float,
    monthly_debt_service: float,
    heloc_interest_monthly: float,
    monthly_salary_draw: float = 6000.0,
) -> float:
    """Months to recoup the down payment while drawing a monthly salary (cap 120)."""
    if down_payment <= 0:
        return 0.0
    cumulative = 0.0
    for month in range(1, 121):
        free_cf = monthly_net - monthly_debt_service - heloc_interest_monthly - monthly_salary_draw
        if free_cf > 0:
            cumulative += free_cf
        if cumulative >= down_payment:
            return float(month)
    return 120.0


# ===========================================================================
# NEW v7 DIMENSION 1 — EXIT POTENTIAL
# ===========================================================================

def _exit_potential_score(category_v2: str, annual_multiple: float) -> tuple[float, str]:
    """Category revenue-multiple ceiling + headroom from the current multiple.

    Two components (moat is deliberately EXCLUDED — defensibility != exit multiple):
      - ceiling  (60%): how high the category's exit multiple ceiling is, normalised
                        against the SaaS ceiling (8x). Rewards structurally
                        high-multiple categories (SaaS, Software/Digital).
      - headroom (40%): how far the current entry multiple sits below the category
                        ceiling. Buying at/below the floor = maximum re-rating upside.

    Returns (score, rationale).
    """
    low, high = CATEGORY_EXIT_MULTIPLE_RANGE.get(category_v2, (2.0, 4.0))

    ceiling_score = _clamp((high / _MAX_EXIT_HIGH) * 100.0)

    if high <= low:
        headroom_score = 50.0
    elif annual_multiple <= 0:
        headroom_score = 100.0            # unknown/free entry — treat as max headroom
    elif annual_multiple >= high:
        headroom_score = 0.0              # already priced at/above the ceiling
    elif annual_multiple <= low:
        headroom_score = 100.0            # bought at/below the floor
    else:
        headroom_score = _clamp((high - annual_multiple) / (high - low) * 100.0)

    score = round(0.6 * ceiling_score + 0.4 * headroom_score, 2)

    rationale = (
        f"{category_v2} exit ceiling {low:g}-{high:g}x; entry multiple "
        f"{annual_multiple:g}x. "
        + (
            "Strong exit setup — high category ceiling with room to re-rate on exit."
            if score >= 65 else
            "Moderate exit setup — either the ceiling is modest or entry is near the ceiling."
            if score >= 40 else
            "Weak exit setup — low category ceiling and/or richly-priced entry."
        )
    )
    return score, rationale


# ===========================================================================
# NEW v7 DIMENSION 2 — PROFIT POTENTIAL (12-lever composite)
# ===========================================================================

# The 12 growth levers and their composite weights (sum to 1.0).
PROFIT_LEVER_WEIGHTS: dict[str, float] = {
    "pricing_optimization": 0.12,
    "channel_geo_expansion": 0.10,
    "product_expansion": 0.10,
    "retention_lifecycle": 0.10,
    "ai_growth_engine": 0.10,
    "brand_awareness": 0.08,
    "pain_severity": 0.08,
    "willingness_to_pay": 0.08,
    "feedback_reputation": 0.06,
    "content_social_presence": 0.06,
    "audience_demographics": 0.06,
    "global_applicability": 0.06,
}

# Per-lever sub-score weights (sum to 1.0). utilization_gap = 100 - current_utilization.
_LEVER_W_UPSIDE = 0.45
_LEVER_W_UTIL_GAP = 0.30
_LEVER_W_FEASIBILITY = 0.15
_LEVER_W_EVIDENCE = 0.10


def _default_lever_profile(
    category_v2: str,
    monthly_net: float,
    peak_monthly_net: float,
    has_enrichment: bool,
) -> dict[str, dict[str, float]]:
    """Deterministic default lever inputs derived from category + deal signals.

    Each lever gets: current_utilization, addable_upside, feasibility,
    evidence_confidence (all 0-100). When no enrichment is supplied, evidence
    confidence is held low (35) so the profit score honestly reflects the gap.
    """
    evidence = 60.0 if has_enrichment else 35.0

    # Neutral baseline for every lever.
    profile: dict[str, dict[str, float]] = {
        lever: {
            "current_utilization": 40.0,
            "addable_upside": 55.0,
            "feasibility": 60.0,
            "evidence_confidence": evidence,
        }
        for lever in PROFIT_LEVER_WEIGHTS
    }

    # --- category tilts -----------------------------------------------------
    if category_v2 in ("SaaS", "Software/Digital"):
        profile["ai_growth_engine"]["addable_upside"] = 75.0
        profile["ai_growth_engine"]["feasibility"] = 70.0
        profile["global_applicability"]["addable_upside"] = 75.0
        profile["product_expansion"]["addable_upside"] = 70.0
        profile["retention_lifecycle"]["feasibility"] = 70.0
    if category_v2 == "Services":
        profile["global_applicability"]["addable_upside"] = 40.0
        profile["global_applicability"]["feasibility"] = 35.0
        profile["pricing_optimization"]["addable_upside"] = 70.0  # under-priced labour
    if category_v2 == "Physical Ecommerce":
        profile["channel_geo_expansion"]["addable_upside"] = 70.0
        profile["ai_growth_engine"]["feasibility"] = 45.0
        profile["global_applicability"]["feasibility"] = 40.0     # logistics-bound
    if category_v2 in ("Content/Media", "Education/Info"):
        profile["content_social_presence"]["current_utilization"] = 55.0
        profile["product_expansion"]["addable_upside"] = 65.0

    # --- signal: neglect / decline means recoverable marketing upside -------
    _peak = peak_monthly_net if peak_monthly_net > 0 else monthly_net
    if _peak > 0 and monthly_net < _peak * 0.85:
        for lever in ("brand_awareness", "content_social_presence", "retention_lifecycle"):
            profile[lever]["current_utilization"] = 25.0   # currently dormant
            profile[lever]["addable_upside"] = 75.0         # high recovery upside

    return profile


def _lever_score(inputs: dict[str, float]) -> float:
    """Blend the four sub-inputs of a single lever into a 0-100 score."""
    util_gap = 100.0 - inputs["current_utilization"]
    return _clamp(
        _LEVER_W_UPSIDE * inputs["addable_upside"]
        + _LEVER_W_UTIL_GAP * util_gap
        + _LEVER_W_FEASIBILITY * inputs["feasibility"]
        + _LEVER_W_EVIDENCE * inputs["evidence_confidence"]
    )


def _profit_potential_score(
    category_v2: str,
    monthly_net: float,
    peak_monthly_net: float,
    moat_score: float,
    enrichment_levers: Optional[dict[str, dict[str, float]]] = None,
) -> tuple[float, dict, str]:
    """Composite growth-headroom score replacing v6's value_add_score.

    Moat is applied as a small MODIFIER (+/-5 pts), never as a lever — that keeps
    defensibility from being double-counted against the growth-lever axes.

    Returns (profit_potential_score, growth_lever_scores, rationale).
    """
    has_enrichment = bool(enrichment_levers)
    profile = _default_lever_profile(category_v2, monthly_net, peak_monthly_net, has_enrichment)

    # Overlay any enrichment-provided lever inputs (partial overlays allowed).
    if enrichment_levers:
        for lever, overrides in enrichment_levers.items():
            if lever in profile and isinstance(overrides, dict):
                profile[lever].update(
                    {k: float(v) for k, v in overrides.items() if k in profile[lever]}
                )

    lever_scores: dict[str, dict[str, float]] = {}
    weighted_sum = 0.0
    for lever, weight in PROFIT_LEVER_WEIGHTS.items():
        s = _lever_score(profile[lever])
        lever_scores[lever] = {
            **{k: round(v, 2) for k, v in profile[lever].items()},
            "lever_score": round(s, 2),
            "weight": weight,
        }
        weighted_sum += weight * s

    # Moat modifier: +/-5 points, centred at moat=50.
    moat_modifier = (moat_score - 50.0) / 50.0 * 5.0
    score = round(_clamp(weighted_sum + moat_modifier), 2)

    top = sorted(
        lever_scores.items(), key=lambda kv: kv[1]["lever_score"], reverse=True
    )[:3]
    top_str = ", ".join(f"{name} ({d['lever_score']:.0f})" for name, d in top)

    rationale = (
        f"Profit-potential composite {score:.0f}/100 across {len(PROFIT_LEVER_WEIGHTS)} "
        f"growth levers (moat modifier {moat_modifier:+.1f}). "
        f"Strongest levers: {top_str}. "
        + (
            "" if has_enrichment else
            "NOTE: no enrichment supplied — lever evidence confidence is low; "
            "scores are category-default estimates pending research."
        )
    ).strip()
    return score, lever_scores, rationale


# ===========================================================================
# NEW v7 DIMENSION 3 — TAM
# ===========================================================================

def _tam_size_band_score(tam_usd: float, sam_usd: float) -> tuple[float, str]:
    """Market-size band component (0-100)."""
    if tam_usd < 25e6:
        return 20.0, "<$25M (weak)"
    if tam_usd < 100e6:
        return 40.0, "$25-100M (small)"
    if tam_usd < 500e6:
        return 60.0, "$100-500M (good)"
    if tam_usd < 2e9:
        return 80.0, "$500M-2B (strong)"
    if tam_usd < 10e9:
        return 95.0, "$2-10B (very strong)"
    # >$10B is only "strong" if a SAM is defined — otherwise it's too broad to trust.
    if sam_usd > 0:
        return 90.0, ">$10B with defined SAM (strong)"
    return 60.0, ">$10B, no SAM (unfocused — capped)"


def _tam_score(
    tam_usd: float = 0.0,
    sam_usd: float = 0.0,
    market_growth_rate_pct: float = 0.0,
    annual_net: float = 0.0,
    tam_confidence_score: float = 0.0,
    tam_source_url: str = "",
) -> tuple[float, str]:
    """Total-addressable-market attractiveness (0-100).

    Weights: 40% size band, 25% growth rate, 25% penetration headroom, 10% source
    confidence. Returns 0 (graceful) when no TAM figure is supplied.

    Returns (score, rationale).
    """
    if not tam_usd or tam_usd <= 0:
        return 0.0, "TAM not supplied — dimension skipped (score 0); enrich tam_usd to activate."

    size_score, size_label = _tam_size_band_score(tam_usd, sam_usd)

    # Growth: 0% -> 0, 20%+ -> 100 (linear).
    growth_score = _clamp((market_growth_rate_pct / 20.0) * 100.0)

    # Penetration headroom: current annual revenue vs TAM. Less penetration = more room.
    # At >=5% penetration headroom collapses to 0; at 0 penetration it is 100.
    if tam_usd > 0 and annual_net > 0:
        penetration = annual_net / tam_usd
        headroom_score = _clamp((1.0 - min(penetration / 0.05, 1.0)) * 100.0)
    else:
        headroom_score = 100.0

    confidence_score = _clamp(tam_confidence_score)

    score = round(
        0.40 * size_score
        + 0.25 * growth_score
        + 0.25 * headroom_score
        + 0.10 * confidence_score,
        2,
    )

    src = "sourced" if tam_source_url else "unsourced"
    rationale = (
        f"TAM {size_label}, growth {market_growth_rate_pct:g}%/yr, "
        f"penetration headroom {headroom_score:.0f}/100, confidence "
        f"{confidence_score:.0f}/100 ({src}). "
        + (
            "Attractive market — large, growing, and under-penetrated."
            if score >= 65 else
            "Adequate market — some combination of size, growth, or headroom is limiting."
            if score >= 40 else
            "Thin market — size/growth/penetration do not support an aggressive thesis."
        )
    )
    return score, rationale


# ===========================================================================
# v7 TIERED COMPETITOR ANALYSIS
# ===========================================================================

def _competitor_analysis_score(
    category_v2: str,
    num_competitors: int = 10,
    niche_growth_score: Optional[float] = None,
    market_fragmentation_score: Optional[float] = None,
    named_competitors: Optional[list] = None,
    estimated_market_share: Optional[float] = None,
) -> tuple[float, str, str]:
    """Tiered competitive-intensity score. Returns (score, research_level, rationale).

    L0 (instant): category base + competitor-count adjustment, optionally blended
                  with niche growth + market fragmentation dynamics.
    L1 (research): additionally incorporates named competitors + estimated market
                   share once those research fields are present.
    L2 is deferred (deep positioning / win-loss analysis — future phase).
    """
    base = CATEGORY_COMPETITOR_BASE.get(category_v2, 50.0)

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
    l0 = base + adjustment

    # Blend in niche dynamics if provided (still L0 — these are instant signals).
    dynamics_parts = []
    if niche_growth_score is not None:
        dynamics_parts.append(_clamp(niche_growth_score))
    if market_fragmentation_score is not None:
        # Fragmented markets are easier to enter/roll-up — treat higher as better.
        dynamics_parts.append(_clamp(market_fragmentation_score))
    if dynamics_parts:
        dynamics = sum(dynamics_parts) / len(dynamics_parts)
        l0 = 0.6 * l0 + 0.4 * dynamics

    score = _clamp(l0)
    research_level = "L0"

    # L1 refinement — requires named competitors AND a market-share estimate.
    if named_competitors and estimated_market_share is not None:
        research_level = "L1"
        share = _clamp(estimated_market_share)  # subject's own share, 0-100
        # Higher own share = stronger position (bounded contribution).
        share_component = _clamp(share)
        # More named competitors named in research = more validated crowding.
        crowd_penalty = min(len(named_competitors) * 3.0, 30.0)
        score = _clamp(0.7 * score + 0.3 * share_component - crowd_penalty * 0.2)

    rationale = (
        f"[{research_level}] {num_competitors} competitor(s) in the {category_v2} niche"
        + (
            f"; {len(named_competitors)} named, subject share ~{estimated_market_share:g}%"
            if research_level == "L1" else ""
        )
        + ". "
        + (
            "Favourable competitive position — pricing power and margin protection."
            if score >= 65 else
            "Workable competitive field — differentiation is the growth lever."
            if score >= 40 else
            "Crowded/commoditised — a durable moat is a prerequisite for this acquisition."
        )
    )
    return round(score, 2), research_level, rationale


# ===========================================================================
# v7 REWEIGHTED COMPOSITE (13 weighted axes, sum to 1.0)
# ===========================================================================

# Explicit weight table so the composite is auditable and testable.
V7_WEIGHTS: dict[str, float] = {
    "cashflow": 0.13,
    "profit_potential": 0.13,
    "exit_potential": 0.12,
    "moat": 0.10,
    "tam": 0.09,
    "competitor_analysis": 0.08,
    "ai_proof": 0.08,
    "company_life": 0.07,
    "buy_vs_build": 0.06,          # rescaled from 0-10 to 0-100 internally
    "mitigation": 0.05,
    "owner_neglect_inverted": 0.04,
    "platform_risk_inverted": 0.03,
    "risk_inverted": 0.02,
}


def _overall_score(
    cashflow: float,
    profit_potential: float,
    exit_potential: float,
    moat: float,
    tam: float,
    competitor_analysis: float,
    ai_proof: float,
    company_life: float,
    buy_vs_build: float,            # 0-10
    mitigation: float,
    owner_neglect: float,           # 0-100, HIGHER = worse -> inverted
    platform_risk: float,           # 0-100, HIGHER = worse -> inverted
    risk_exposure: float,           # 0-100, HIGHER = worse -> inverted
) -> float:
    """Weighted composite on 0-100, normalised to 0-10. See V7_WEIGHTS."""
    buy_vs_build_normalized = buy_vs_build * 10.0
    composite = (
        cashflow                              * V7_WEIGHTS["cashflow"]
        + profit_potential                    * V7_WEIGHTS["profit_potential"]
        + exit_potential                      * V7_WEIGHTS["exit_potential"]
        + moat                                * V7_WEIGHTS["moat"]
        + tam                                 * V7_WEIGHTS["tam"]
        + competitor_analysis                 * V7_WEIGHTS["competitor_analysis"]
        + ai_proof                            * V7_WEIGHTS["ai_proof"]
        + company_life                        * V7_WEIGHTS["company_life"]
        + buy_vs_build_normalized             * V7_WEIGHTS["buy_vs_build"]
        + mitigation                          * V7_WEIGHTS["mitigation"]
        + (100.0 - owner_neglect)             * V7_WEIGHTS["owner_neglect_inverted"]
        + (100.0 - platform_risk)             * V7_WEIGHTS["platform_risk_inverted"]
        + (100.0 - risk_exposure)             * V7_WEIGHTS["risk_inverted"]
    )
    return round(_clamp(composite / 10.0, 0.0, 10.0), 2)


# ===========================================================================
# GENERIC RATIONALES (no case-study hardcoding)
# ===========================================================================

def _build_rationales(
    category_v2: str,
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
    buy_vs_build_score: float,
    buy_vs_build_decision: str,
    risk_score: float,
    risk_flags: list,
    mitigation_score: float,
    mitigation_actions: list,
    company_life_score: float,
    company_life_months: float,
    company_life_label: str,
) -> dict:
    """One generic, deal-agnostic rationale sentence per preserved dimension."""
    rationales: dict[str, str] = {}

    annual_net = monthly_net * 12
    multiple = round(asking_price / annual_net, 1) if annual_net > 0 else 0
    rationales["cashflow_score"] = (
        f"Generating ${monthly_net:,.0f}/mo (${annual_net:,.0f}/yr) at a {multiple}x annual multiple — "
        + ("strong cashflow engine relative to asking price."
           if cashflow_score >= 60 else
           "below benchmark but cash-flow positive; recovery upside justifies entry."
           if cashflow_score >= 30 else
           "low current yield; thesis depends on growth recovery.")
    )

    moat_drivers = []
    if has_sdk_integration:  moat_drivers.append("platform/SDK lock-in (+15)")
    if has_proprietary_data: moat_drivers.append("proprietary data/IP (+10)")
    if has_network_effect:   moat_drivers.append("network effect (+12)")
    if num_competitors < 5:  moat_drivers.append(f"only {num_competitors} competitor(s) (+10)")
    driver_str = ", ".join(moat_drivers) if moat_drivers else "category and age only"
    rationales["moat_score"] = (
        f"{age_years:.0f}-year-old {category_v2} business; defensibility from {driver_str} — "
        + ("deep moat, hard to replicate within 12 months."
           if moat_score >= 75 else
           "moderate moat, replication non-trivial."
           if moat_score >= 50 else
           "shallow moat, vulnerable to fast followers.")
    )

    rationales["ai_proof_score"] = (
        f"{category_v2} baseline gives {ai_proof_score:.0f}/100 AI-disruption resistance — "
        + ("well-insulated; AI augments rather than replaces this niche."
           if ai_proof_score >= 75 else
           "moderate exposure; monitor AI tooling over 12-18 months."
           if ai_proof_score >= 55 else
           "high AI-disruption risk; a strong differentiation moat is required.")
    )

    rationales["company_life_score"] = (
        f"If left untouched, ~{company_life_months:.0f} months of runway — '{company_life_label}'. "
        + ("Survives benign neglect; moat slows churn decay."
           if company_life_label in ("Growing / Durable", "Stable") else
           "Revenue erodes within 2 years without active ownership."
           if company_life_label == "Declining" else
           "Terminal trajectory without immediate intervention.")
    )

    bvb_label = buy_vs_build_decision.upper()
    rationales["buy_vs_build_score"] = (
        f"Decision: {bvb_label} — score {buy_vs_build_score:.1f}/10. "
        + ("Buying justified: moat depth makes replication slow and costly for a new entrant."
           if buy_vs_build_decision == "buy" else
           "Building justified: shallow moat means a greenfield build can match this at lower cost."
           if buy_vs_build_decision == "build" else
           "Hybrid: acquire the customer base or IP while rebuilding the tech stack.")
    )

    rationales["risk_score"] = (
        f"{len(risk_flags)} risk factor(s) — exposure {risk_score:.0f}/100 (higher = worse). "
        + ("High exposure; requires a strong mitigation plan and tight DD."
           if risk_score >= 65 else
           "Moderate risk; manageable with transition planning."
           if risk_score >= 40 else
           "Low risk; structurally sound with limited downside triggers.")
    )

    rationales["mitigation_score"] = (
        f"{len(mitigation_actions)} mitigation lever(s) — score {mitigation_score:.0f}/100. "
        + ("Strong offset capability; most risks neutralisable within 90 days."
           if mitigation_score >= 70 else
           "Moderate mitigation; key risks addressable with deliberate execution."
           if mitigation_score >= 50 else
           "Limited mitigation; risk acceptance is the primary strategy.")
    )

    return rationales


def _bucket_rationales(
    score_rationales: dict,
    owner_neglect_rationale: str,
    platform_risk_rationale: str,
    exit_rationale: str,
    profit_rationale: str,
    tam_rationale: str,
    competitor_rationale: str,
    breakeven_months: float,
    down_payment: float,
    monthly_salary_draw: float,
) -> dict:
    """Group rationales into category buckets (v7: adds Market & Exit)."""
    return {
        "Financial": {
            "cashflow_score": score_rationales.get("cashflow_score", ""),
            "buy_vs_build_score": score_rationales.get("buy_vs_build_score", ""),
            "breakeven_with_draw": (
                f"Drawing ${monthly_salary_draw:,.0f}/mo: down payment ${down_payment:,.0f} "
                f"recovered in ~{breakeven_months:.0f} months ({breakeven_months / 12:.1f} yrs). "
                + (
                    "Fast payback — acquisition self-liquidates quickly."
                    if breakeven_months <= 12 else
                    "Moderate payback — cashflow covers the draw with patience on capital."
                    if breakeven_months <= 24 else
                    "Extended payback — consider reducing the early draw to accelerate recovery."
                )
            ),
        },
        "Market & Exit": {
            "exit_potential_score": exit_rationale,
            "tam_score": tam_rationale,
            "profit_potential_score": profit_rationale,
        },
        "Moat & Defense": {
            "moat_score": score_rationales.get("moat_score", ""),
            "ai_proof_score": score_rationales.get("ai_proof_score", ""),
            "competitor_analysis_score": competitor_rationale,
            "company_life_score": score_rationales.get("company_life_score", ""),
        },
        "Risk & Mitigation": {
            "risk_score": score_rationales.get("risk_score", ""),
            "mitigation_score": score_rationales.get("mitigation_score", ""),
        },
        "Platform Risk": {
            "platform_dependency_risk_score": platform_risk_rationale,
        },
        "Operator Profile": {
            "owner_neglect_score": owner_neglect_rationale,
        },
    }


# ===========================================================================
# PUBLIC ENTRY POINT — analyze_deal_v7
# ===========================================================================

def analyze_deal_v7(
    deal: "DealV7",
    enrichment: Optional[dict] = None,
    *,
    num_competitors: int = 10,
    has_sdk_integration: bool = False,
    has_proprietary_data: bool = False,
    has_network_effect: bool = False,
    single_owner_dependent: bool = False,
    peak_monthly_net: float = 0.0,
    financing_required: bool = True,
    revenue_floor: float = 500.0,
    owner_neglect_months: int = 0,
    owner_is_sole_operator: bool = False,
    platform_native_overlap_pct: float = 0.0,
    platform_name: str = "the host platform",
    monthly_salary_draw: float = 6000.0,
    **_ignored: Any,
) -> "DealV7":
    """Score a deal with the v7 engine and return an updated DealV7 copy.

    Fully deterministic — no network, no LLM. Backward compatible: with no
    `enrichment` and no v7 kwargs it scores everything it can and flags gaps
    (tam_score -> 0, competitor stays L0, profit levers use low-confidence
    category defaults).

    `enrichment` is an optional dict that may contain:
        tam_usd, sam_usd, market_growth_rate_pct, tam_source_url,
        tam_confidence_score,
        niche_growth_score, market_fragmentation_score,
        named_competitors (list), estimated_market_share (float),
        growth_levers (dict[str, dict] of lever input overrides),
        platform_name, platform_native_overlap_pct,
        num_competitors, has_sdk_integration, has_proprietary_data,
        has_network_effect, single_owner_dependent, peak_monthly_net,
        owner_neglect_months, owner_is_sole_operator, financing_required.
    Values in `enrichment` override the corresponding keyword defaults.
    """
    enr = dict(enrichment or {})

    # enrichment dict overrides keyword defaults for shared knobs.
    num_competitors = int(enr.get("num_competitors", num_competitors))
    has_sdk_integration = bool(enr.get("has_sdk_integration", has_sdk_integration))
    has_proprietary_data = bool(enr.get("has_proprietary_data", has_proprietary_data))
    has_network_effect = bool(enr.get("has_network_effect", has_network_effect))
    single_owner_dependent = bool(enr.get("single_owner_dependent", single_owner_dependent))
    financing_required = bool(enr.get("financing_required", financing_required))
    peak_monthly_net = float(enr.get("peak_monthly_net", peak_monthly_net))
    owner_neglect_months = int(enr.get("owner_neglect_months", owner_neglect_months))
    owner_is_sole_operator = bool(enr.get("owner_is_sole_operator", owner_is_sole_operator))
    platform_native_overlap_pct = float(
        enr.get("platform_native_overlap_pct", platform_native_overlap_pct)
    )
    platform_name = str(enr.get("platform_name", platform_name))

    d = deal.model_copy(deep=True)
    _peak = peak_monthly_net if peak_monthly_net > 0 else d.monthly_net

    # ---- taxonomy: derive category_v2 -------------------------------------
    hint = f"{d.name} {d.notes}"
    d.category_v2 = migrate_category(d.category, hint=hint)
    cat = d.category_v2

    # ---- preserved axes ----------------------------------------------------
    d.cashflow_score = round(_cashflow_score(d.monthly_net), 2)

    d.moat_score = round(
        _moat_score(
            d.age_years, cat, num_competitors=num_competitors,
            has_sdk_integration=has_sdk_integration,
            has_proprietary_data=has_proprietary_data,
            has_network_effect=has_network_effect,
        ), 2,
    )

    if d.ai_proof_score == 0.0:
        d.ai_proof_score = round(_ai_proof_score(d.age_years, cat), 2)

    if d.buy_vs_build_score == 0.0:
        d.buy_vs_build_score = round(_buy_vs_build_score(d.buy_vs_build_decision, d.moat_score), 2)

    raw_risk, risk_flags = _risk_score(
        age_years=d.age_years, category_v2=cat, monthly_net=d.monthly_net,
        peak_monthly_net=_peak, num_competitors=num_competitors,
        has_sdk_integration=has_sdk_integration,
        single_owner_dependent=single_owner_dependent,
        financing_required=financing_required,
    )
    d.risk_score = round(raw_risk, 2)
    d.risk_flags = risk_flags

    raw_mitigation, mitigation_actions = _mitigation_score(
        category_v2=cat, moat_score=d.moat_score,
        has_sdk_integration=has_sdk_integration,
        has_proprietary_data=has_proprietary_data,
        monthly_net=d.monthly_net, peak_monthly_net=_peak,
        age_years=d.age_years, num_competitors=num_competitors,
    )
    d.mitigation_score = round(raw_mitigation, 2)
    d.mitigation_actions = mitigation_actions

    months, life_score, life_label = _company_life(d.monthly_net, cat, d.moat_score, revenue_floor)
    d.company_life_months = months
    d.company_life_score = life_score
    d.company_life_label = life_label

    owner_neglect_raw, owner_neglect_rationale = _owner_neglect_score(
        monthly_net=d.monthly_net, peak_monthly_net=_peak,
        owner_neglect_months=owner_neglect_months,
        owner_is_sole_operator=owner_is_sole_operator,
    )
    d.owner_neglect_score = owner_neglect_raw

    # ---- v7: platform dependency risk (generalised) -----------------------
    platform_risk_raw, platform_risk_rationale = _platform_dependency_risk_score(
        category_v2=cat, has_sdk_integration=has_sdk_integration,
        platform_native_overlap_pct=platform_native_overlap_pct,
        platform_name=platform_name,
    )
    d.platform_dependency_risk_score = platform_risk_raw

    # ---- v7 NEW: exit potential -------------------------------------------
    exit_score, exit_rationale = _exit_potential_score(cat, d.annual_multiple)
    d.exit_potential_score = exit_score

    # ---- v7 NEW: profit potential (12 levers) -----------------------------
    profit_score, lever_scores, profit_rationale = _profit_potential_score(
        category_v2=cat, monthly_net=d.monthly_net, peak_monthly_net=_peak,
        moat_score=d.moat_score,
        enrichment_levers=enr.get("growth_levers"),
    )
    d.profit_potential_score = profit_score
    d.profit_lever_scores = lever_scores

    # ---- v7 NEW: TAM -------------------------------------------------------
    d.tam_usd = float(enr.get("tam_usd", d.tam_usd or 0.0))
    d.sam_usd = float(enr.get("sam_usd", d.sam_usd or 0.0))
    d.market_growth_rate_pct = float(
        enr.get("market_growth_rate_pct", d.market_growth_rate_pct or 0.0)
    )
    d.tam_confidence = float(enr.get("tam_confidence_score", d.tam_confidence or 0.0))
    tam_source_url = str(enr.get("tam_source_url", ""))

    tam_score, tam_rationale = _tam_score(
        tam_usd=d.tam_usd, sam_usd=d.sam_usd,
        market_growth_rate_pct=d.market_growth_rate_pct,
        annual_net=d.monthly_net * 12.0,
        tam_confidence_score=d.tam_confidence,
        tam_source_url=tam_source_url,
    )
    d.tam_score = tam_score

    # ---- v7: tiered competitor analysis -----------------------------------
    d.named_competitors = list(enr.get("named_competitors", d.named_competitors or []))
    if "estimated_market_share" in enr:
        d.estimated_market_share = float(enr["estimated_market_share"])
    if "niche_growth_score" in enr:
        d.niche_growth_score = float(enr["niche_growth_score"])
    if "market_fragmentation_score" in enr:
        d.market_fragmentation_score = float(enr["market_fragmentation_score"])

    comp_score, research_level, competitor_rationale = _competitor_analysis_score(
        category_v2=cat, num_competitors=num_competitors,
        niche_growth_score=d.niche_growth_score,
        market_fragmentation_score=d.market_fragmentation_score,
        named_competitors=d.named_competitors or None,
        estimated_market_share=d.estimated_market_share,
    )
    d.competitor_analysis_score = comp_score
    d.research_level = research_level

    # ---- v7 composite ------------------------------------------------------
    d.overall_score = _overall_score(
        cashflow=d.cashflow_score,
        profit_potential=d.profit_potential_score,
        exit_potential=d.exit_potential_score,
        moat=d.moat_score,
        tam=d.tam_score,
        competitor_analysis=d.competitor_analysis_score,
        ai_proof=d.ai_proof_score,
        company_life=d.company_life_score,
        buy_vs_build=d.buy_vs_build_score,
        mitigation=d.mitigation_score,
        owner_neglect=d.owner_neglect_score,
        platform_risk=d.platform_dependency_risk_score,
        risk_exposure=d.risk_score,
    )

    # ---- financial analysis (preserved v6 model) --------------------------
    d.down_payment = round(d.asking_price * 0.20, 2)
    d.seller_finance_amount = round(d.asking_price * 0.80, 2)
    d.monthly_debt_service = round(_pmt(0.07, 60, d.seller_finance_amount), 2)
    d.net_monthly_cashflow = round(d.monthly_net - d.monthly_debt_service, 2)
    d.heloc_used = d.down_payment
    d.heloc_interest_monthly = round(d.heloc_used * 0.095 / 12.0, 2)
    d.net_after_heloc = round(d.net_monthly_cashflow - d.heloc_interest_monthly, 2)
    d.breakeven_months_with_draw = _breakeven_with_draw(
        down_payment=d.down_payment, monthly_net=d.monthly_net,
        monthly_debt_service=d.monthly_debt_service,
        heloc_interest_monthly=d.heloc_interest_monthly,
        monthly_salary_draw=monthly_salary_draw,
    )

    # ---- rationales --------------------------------------------------------
    d.score_rationales = _build_rationales(
        category_v2=cat, age_years=d.age_years, monthly_net=d.monthly_net,
        asking_price=d.asking_price, num_competitors=num_competitors,
        has_sdk_integration=has_sdk_integration,
        has_proprietary_data=has_proprietary_data,
        has_network_effect=has_network_effect,
        cashflow_score=d.cashflow_score, moat_score=d.moat_score,
        ai_proof_score=d.ai_proof_score, buy_vs_build_score=d.buy_vs_build_score,
        buy_vs_build_decision=d.buy_vs_build_decision, risk_score=d.risk_score,
        risk_flags=d.risk_flags, mitigation_score=d.mitigation_score,
        mitigation_actions=d.mitigation_actions, company_life_score=d.company_life_score,
        company_life_months=d.company_life_months, company_life_label=d.company_life_label,
    )
    # Surface the new-dimension rationales alongside the preserved ones.
    d.score_rationales["exit_potential_score"] = exit_rationale
    d.score_rationales["profit_potential_score"] = profit_rationale
    d.score_rationales["tam_score"] = tam_rationale
    d.score_rationales["competitor_analysis_score"] = competitor_rationale
    d.score_rationales["platform_dependency_risk_score"] = platform_risk_rationale
    d.score_rationales["owner_neglect_score"] = owner_neglect_rationale

    d.score_buckets = _bucket_rationales(
        score_rationales=d.score_rationales,
        owner_neglect_rationale=owner_neglect_rationale,
        platform_risk_rationale=platform_risk_rationale,
        exit_rationale=exit_rationale, profit_rationale=profit_rationale,
        tam_rationale=tam_rationale, competitor_rationale=competitor_rationale,
        breakeven_months=d.breakeven_months_with_draw,
        down_payment=d.down_payment, monthly_salary_draw=monthly_salary_draw,
    )

    d.scoring_version = "7.0.0"
    d.updated_at = datetime.now(timezone.utc).isoformat()
    return d
