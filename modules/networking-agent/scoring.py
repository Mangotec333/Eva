"""
EVA Networking-Agent — group scoring (deterministic, unit-testable).

Produces a single 0–1 ``score`` for a candidate group plus a confidence band
(high / med / low). The score is a weighted blend of four normalised inputs:

    score = W_MEMBERS   * member_norm
          + W_ACTIVITY   * activity_score
          + W_TOPICAL    * topical_fit_score
          + W_ACCESS     * access_ease

Weights (sum to 1.0):
    topical fit   0.40   — a perfectly-on-ICP room beats a big off-topic one.
    activity      0.30   — a dead group is worthless regardless of size.
    member count  0.20   — reach matters, but with diminishing returns.
    access ease   0.10   — public rooms are cheaper to enter than invite-only.

Normalisation
  * member_norm: log-scaled against ``MEMBER_SATURATION`` (default 50k) so a
    500-member niche room isn't buried by a 500k generalist one; capped at 1.0.
  * activity_score / topical_fit_score: expected already in [0, 1]; clamped.
  * access_ease: public=1.0, private=0.7, paid=0.5, invite_only=0.4 (rarity of a
    room can be worth the friction, so invite-only isn't zeroed).

Confidence band reflects how much signal we actually had: a group scored with
default/zero activity and topical fit gets a lower band even if members are high.
Everything here is pure and side-effect-free.
"""

from __future__ import annotations

import math

W_TOPICAL = 0.40
W_ACTIVITY = 0.30
W_MEMBERS = 0.20
W_ACCESS = 0.10

MEMBER_SATURATION = 50_000

ACCESS_EASE = {
    "public": 1.0,
    "private": 0.7,
    "paid": 0.5,
    "invite_only": 0.4,
}


def _clamp01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return float(x)


def member_norm(member_count: int) -> float:
    """Log-scaled member reach in [0, 1] (diminishing returns, capped)."""
    n = max(0, int(member_count or 0))
    if n <= 0:
        return 0.0
    return _clamp01(math.log10(n + 1) / math.log10(MEMBER_SATURATION + 1))


def access_ease(access_type: str) -> float:
    return ACCESS_EASE.get((access_type or "public").strip().lower(), 0.7)


def confidence_band(group: dict) -> str:
    """How much real signal fed the score (not the score's magnitude)."""
    activity = _clamp01(float(group.get("activity_score", 0) or 0))
    topical = _clamp01(float(group.get("topical_fit_score", 0) or 0))
    members = int(group.get("member_count", 0) or 0)
    signals = sum([activity > 0, topical > 0, members > 0])
    if signals == 3 and topical >= 0.5 and activity >= 0.4:
        return "high"
    if signals >= 2:
        return "med"
    return "low"


def score_group(group: dict) -> dict:
    """Return ``{score, confidence, components}`` for a candidate group dict."""
    activity = _clamp01(float(group.get("activity_score", 0) or 0))
    topical = _clamp01(float(group.get("topical_fit_score", 0) or 0))
    m_norm = member_norm(group.get("member_count", 0))
    a_ease = access_ease(group.get("access_type", "public"))

    score = (
        W_TOPICAL * topical
        + W_ACTIVITY * activity
        + W_MEMBERS * m_norm
        + W_ACCESS * a_ease
    )
    score = round(_clamp01(score), 4)
    return {
        "score": score,
        "confidence": confidence_band(group),
        "components": {
            "topical_fit": round(topical, 4),
            "activity": round(activity, 4),
            "member_norm": round(m_norm, 4),
            "access_ease": round(a_ease, 4),
        },
    }


__all__ = [
    "score_group", "member_norm", "access_ease", "confidence_band",
    "W_TOPICAL", "W_ACTIVITY", "W_MEMBERS", "W_ACCESS",
    "MEMBER_SATURATION", "ACCESS_EASE",
]
