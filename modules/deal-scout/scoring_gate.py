"""
EVA Deal Scout — scoring gate (LLM-credit saver).

The v6 11-param composite is only run on raw deals that pass the gate.  This
avoids spending scorer credits on listings that are neither US-relevant nor
sourced from a high-trust marketplace.

Rules (per spec)
----------------
    US_eligible = registration_country == US
               OR primary_customer_market == US
               OR seller_location == US

    trust_high  = source vetting level is "high" (Empire Flippers today).
                  A high-trust source *bypasses* the US filter.

    GATE PASSES if  US_eligible OR trust_high.

Closed / sold comps are ingested for ALL geographies and are never gated — they
feed the trend analyzer, not the scorer.  Non-scored open deals stay stored raw.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline_models import RawDeal

US_TOKENS = {"US", "USA", "UNITED STATES"}


def is_us_eligible(deal: RawDeal) -> bool:
    for val in (deal.registration_country, deal.primary_customer_market, deal.seller_location):
        if (val or "").strip().upper() in US_TOKENS:
            return True
    return False


def is_trust_high(deal: RawDeal) -> bool:
    return (deal.trust_level or "").lower() == "high"


@dataclass
class GateDecision:
    should_score: bool
    us_eligible: bool
    trust_high: bool
    reason: str


def evaluate(deal: RawDeal) -> GateDecision:
    """Decide whether a raw deal should be handed to the scorer."""
    us = is_us_eligible(deal)
    trust = is_trust_high(deal)

    if deal.is_closed:
        return GateDecision(False, us, trust, "closed comp — not scored (feeds trends)")

    if trust and us:
        reason = "high-trust source and US-eligible"
    elif trust:
        reason = "high-trust source bypasses US filter"
    elif us:
        reasons = []
        if (deal.registration_country or "").upper() in US_TOKENS:
            reasons.append("registration_country=US")
        if (deal.primary_customer_market or "").upper() in US_TOKENS:
            reasons.append("primary_customer_market=US")
        if (deal.seller_location or "").upper() in US_TOKENS:
            reasons.append("seller_location=US")
        reason = "US-eligible (" + ", ".join(reasons) + ")"
    else:
        return GateDecision(False, us, trust, "skipped — not US-eligible and not high-trust")

    return GateDecision(True, us, trust, reason)
