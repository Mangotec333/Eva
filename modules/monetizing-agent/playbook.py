"""
EVA Monetizing Agent — playbook + scoring model (deterministic core)
====================================================================

This is the authoritative, FREE, offline-testable core of the agent (the brain
in ``brain.py`` only sharpens packaging copy on top of it). It implements two
things from the operating doctrine:

1. The 9-play playbook (Reactivate, Upsell, Outreach, Productize, Revive,
   Referral, Content-to-offer, Retainer, White-label) and the rules that MATCH a
   mined signal to a play.
2. The scoring model — Cash Proximity 35 / Effort 20 / Strategic Fit 20 /
   Reusability 15 / Urgency 10 — producing a 0–100 composite used to rank plays
   into the Sunday brief.

Everything is pure: same inputs -> same scores. No network, no clock dependence
(``urgency`` reads a signal field, not wall-clock), so tests are deterministic.
"""

from __future__ import annotations

from typing import Any

# The nine plays. Order is the doctrine's order.
PLAYS = [
    "Reactivate",
    "Upsell",
    "Outreach",
    "Productize",
    "Revive",
    "Referral",
    "Content-to-offer",
    "Retainer",
    "White-label",
]

# Scoring weights (sum = 1.0). From the doctrine's scoring table.
WEIGHTS = {
    "cash_proximity": 0.35,
    "effort": 0.20,
    "strategic_fit": 0.20,
    "reusability": 0.15,
    "urgency": 0.10,
}

# Per-play priors: how repeatable/strategic each play tends to be, and the
# typical effort to execute a packaged artifact. Each on a 0–100 scale where
# HIGHER IS BETTER (for effort, higher = LESS effort). These are priors the
# signal can still override via explicit fields.
_PLAY_PRIORS = {
    #                       effort  reusability  strategic_fit
    "Reactivate":          (85,     30,          60),
    "Upsell":              (80,     55,          70),
    "Outreach":            (75,     40,          60),
    "Productize":          (40,     95,          85),
    "Revive":              (70,     30,          55),
    "Referral":            (85,     45,          65),
    "Content-to-offer":    (70,     75,          70),
    "Retainer":            (55,     90,          85),
    "White-label":         (35,     95,          90),
}


# ---------------------------------------------------------------------------
# Match: mined signal -> play type
# ---------------------------------------------------------------------------

def match_play(signal: dict) -> str:
    """Map a mined signal to exactly one play from the fixed playbook.

    Rules are checked most-specific first. A signal may carry an explicit
    ``suggested_play`` (from a richer upstream source) which wins if valid.
    """
    suggested = signal.get("suggested_play")
    if suggested in PLAYS:
        return suggested

    kind = (signal.get("kind") or "").lower()
    stage = (signal.get("stage") or "").lower()
    engagement = float(signal.get("engagement", 0) or 0)
    age_days = float(signal.get("age_days", 0) or 0)
    lost_days = float(signal.get("lost_days", 0) or 0)

    # Lost/dead deal older than 30 days -> Revive (new angle).
    if kind in ("lost_deal", "dead_deal") or lost_days > 30:
        return "Revive"
    # Waitlist / enriched contact that never got a sales touch -> Outreach.
    if kind in ("waitlist", "waitlist_signup", "new_contact") and engagement == 0:
        return "Outreach"
    # Repeated activity / spec / shipped code -> Productize.
    if kind in ("spec", "drive_spec", "repo_commit", "shipped_work", "asset"):
        return "Productize"
    # A GHL workflow / Eva feature -> White-label / resale.
    if kind in ("workflow", "feature", "resale_unit"):
        return "White-label"
    # One-off service delivered -> Retainer.
    if kind in ("one_off", "completed_service", "invoice_paid"):
        return "Retainer"
    # Content activity with no CTA -> Content-to-offer.
    if kind in ("content", "linkedin", "youtube", "post") and not signal.get("has_cta", False):
        return "Content-to-offer"
    # Happy / high-engagement contact -> Referral.
    if engagement >= 5 and stage in ("won", "customer", "client", "closed"):
        return "Referral"
    # Existing engaged contact -> Upsell.
    if engagement >= 2 and kind in ("contact", "customer", "engagement"):
        return "Upsell"
    # Cold lead / stalled pipeline -> Reactivate (the default re-engagement play).
    return "Reactivate"


# ---------------------------------------------------------------------------
# Score: 5-dimension composite (0–100)
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_dimensions(signal: dict, play_type: str) -> dict[str, float]:
    """Return the five 0–100 dimension scores (higher = better everywhere)."""
    effort_prior, reuse_prior, fit_prior = _PLAY_PRIORS.get(play_type, (60, 50, 60))

    # Cash proximity: steps to money. A ready-to-pay/engaged lead scores high; a
    # cold list scores low. Signal may pass an explicit 0–100 ``cash_proximity``.
    if "cash_proximity" in signal:
        cash = float(signal["cash_proximity"])
    else:
        engagement = float(signal.get("engagement", 0) or 0)
        stage = (signal.get("stage") or "").lower()
        stage_bonus = {"demo": 30, "proposal": 45, "negotiation": 60,
                       "won": 20, "customer": 40, "client": 40}.get(stage, 0)
        cash = 20 + min(engagement, 10) * 4 + stage_bonus
    cash = _clamp(cash)

    # Effort: prior unless the signal declares an explicit effort_hours.
    if "effort_hours" in signal:
        # More hours -> lower score. 0h -> 100, 20h+ -> ~0.
        effort = _clamp(100 - float(signal["effort_hours"]) * 5)
    else:
        effort = float(effort_prior)

    strategic = _clamp(float(signal.get("strategic_fit", fit_prior)))
    reusability = _clamp(float(signal.get("reusability", reuse_prior)))

    # Urgency: decay window. Prefer an explicit urgency; else derive from a decay
    # window in days (sooner it goes cold -> more urgent).
    if "urgency" in signal:
        urgency = float(signal["urgency"])
    else:
        decay = signal.get("decay_days")
        if decay is None:
            age = float(signal.get("age_days", 0) or 0)
            urgency = _clamp(30 + age * 2)  # older = more urgent to touch
        else:
            urgency = _clamp(100 - float(decay) * 8)  # closer window = urgent
    urgency = _clamp(urgency)

    return {
        "cash_proximity": cash,
        "effort": effort,
        "strategic_fit": strategic,
        "reusability": reusability,
        "urgency": urgency,
    }


def composite_score(dimensions: dict[str, float]) -> float:
    """Weighted composite (0–100), rounded to 2 dp."""
    total = sum(WEIGHTS[k] * float(dimensions.get(k, 0)) for k in WEIGHTS)
    return round(total, 2)


def cash_estimate(signal: dict, dimensions: dict[str, float]) -> float:
    """Best-effort dollar estimate for the brief.

    Uses an explicit ``cash_estimate`` if the signal carries one; otherwise a
    coarse proxy from cash-proximity (kept intentionally simple — this is a
    directional number for ranking/reporting, not accounting).
    """
    if "cash_estimate" in signal:
        return round(float(signal["cash_estimate"]), 2)
    return round(dimensions.get("cash_proximity", 0) * 40, 2)


def score_signal(signal: dict) -> dict[str, Any]:
    """Full deterministic pass for one signal: match -> score -> estimate."""
    play_type = match_play(signal)
    dims = score_dimensions(signal, play_type)
    score = composite_score(dims)
    return {
        "play_type": play_type,
        "dimensions": dims,
        "score": score,
        "cash_estimate": cash_estimate(signal, dims),
        "signal": signal,
    }


__all__ = [
    "PLAYS",
    "WEIGHTS",
    "match_play",
    "score_dimensions",
    "composite_score",
    "cash_estimate",
    "score_signal",
]
