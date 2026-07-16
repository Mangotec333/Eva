"""
EVA IP-Scout — novelty scoring + confidence bands.

Deterministic, explainable scoring (no ML, no network) so triage is repeatable
and testable. Two independent axes:

  * novelty_score ∈ [0, 1] — how distinct the idea looks from the prior-art hits.
    Starts optimistic (1.0) and is penalised by token OVERLAP against each hit
    (the more the idea's terms already appear in prior art, the less novel), with
    a small bonus for CLAIM SPECIFICITY (more distinct claim terms → a tighter,
    more defensible idea).

  * confidence_band ∈ {low, med, high} — how much we trust the assessment, driven
    by how much prior-art evidence we actually examined. Few/no hits examined (or
    an offline/failed provider) → low confidence; lots of hits → high.

IMPORTANT (L1 autonomy): this NEVER asserts patentability. A high novelty_score
means "looks distinct, worth an attorney's review", not "is patentable".
"""

from __future__ import annotations

from provider import tokenize

# recommendation thresholds on novelty_score
FILE_THRESHOLD = 0.66
DROP_THRESHOLD = 0.40

CONFIDENCE_HIGH_HITS = 8
CONFIDENCE_MED_HITS = 3


def _overlap_ratio(idea_tokens: set[str], hit_text: str) -> float:
    """Fraction of the idea's tokens that also appear in this prior-art hit."""
    if not idea_tokens:
        return 0.0
    hit_tokens = set(tokenize(hit_text))
    if not hit_tokens:
        return 0.0
    return len(idea_tokens & hit_tokens) / len(idea_tokens)


def claim_specificity(claims_draft: list[str]) -> float:
    """Specificity bonus ∈ [0, 0.2] from the count of distinct claim terms.
    A richer, more specific claim set nudges novelty up."""
    terms: set[str] = set()
    for claim in claims_draft or []:
        terms.update(tokenize(claim))
    return min(0.20, len(terms) / 60.0)


def score(idea_text: str, hits: list[dict], claims_draft: list[str] | None = None,
          *, provider_ok: bool = True) -> dict:
    """Compute novelty_score + confidence_band + recommendation for one idea.

    idea_text     — title + description (the thing being triaged).
    hits          — normalized prior-art hits from a provider.
    claims_draft  — the drafted claims (for the specificity bonus).
    provider_ok   — False if the provider errored (forces low confidence).
    """
    idea_tokens = set(tokenize(idea_text))
    hits = hits or []

    overlaps = sorted(
        (_overlap_ratio(idea_tokens, f"{h.get('title', '')} {h.get('abstract', '')}")
         for h in hits),
        reverse=True,
    )
    # Penalty is dominated by the closest matches (top-3 mean), so one very close
    # hit matters more than many distant ones.
    top = overlaps[:3]
    overlap_signal = sum(top) / len(top) if top else 0.0

    specificity = claim_specificity(claims_draft or [])
    raw = 1.0 - (overlap_signal * 0.9) + specificity
    novelty_score = round(max(0.0, min(1.0, raw)), 3)

    hits_examined = len(hits)
    if not provider_ok or hits_examined == 0:
        confidence_band = "low"
    elif hits_examined >= CONFIDENCE_HIGH_HITS:
        confidence_band = "high"
    elif hits_examined >= CONFIDENCE_MED_HITS:
        confidence_band = "med"
    else:
        confidence_band = "low"

    recommendation = _recommend(novelty_score, confidence_band)

    return {
        "novelty_score": novelty_score,
        "confidence_band": confidence_band,
        "recommendation": recommendation,
        "prior_art_count": hits_examined,
        "top_overlap": round(overlap_signal, 3),
        "claim_specificity": round(specificity, 3),
        # L1: anything not confidently a drop is worth a human attorney's eyes.
        "attorney_review_needed": recommendation != "drop",
    }


def _recommend(novelty_score: float, confidence_band: str) -> str:
    """Map score → file / monitor / drop. Low confidence never confidently
    files OR drops — it caps out at 'monitor' (we don't have enough evidence)."""
    if confidence_band == "low":
        return "monitor" if novelty_score >= DROP_THRESHOLD else "drop"
    if novelty_score >= FILE_THRESHOLD:
        return "file"
    if novelty_score >= DROP_THRESHOLD:
        return "monitor"
    return "drop"


__all__ = [
    "score", "claim_specificity", "FILE_THRESHOLD", "DROP_THRESHOLD",
    "CONFIDENCE_HIGH_HITS", "CONFIDENCE_MED_HITS",
]
