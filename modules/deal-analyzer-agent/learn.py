"""
EVA Deal Analyzer Agent — LEARNING LOOP
=======================================

The mechanism by which the agent "learns over time" from deal OUTCOMES. It is
deliberately NON-DESTRUCTIVE:

    record_outcome()  -> append an outcome (passed / LOI / closed / ...) to the
                         `learnings` table.
    recalibrate()     -> read all learnings, correlate each scoring dimension
                         with positive vs negative outcomes, and PROPOSE weight
                         deltas. It does NOT mutate the base weights; it logs the
                         proposal to `directive_versions` for human/agent review.
    apply_learning()  -> once a proposal is reviewed, persist the deltas into a
                         LEARNED_WEIGHTS override file that scoring_v7 consumes via
                         analyze_deal_v7(weights_override=...). Logs the apply.
    get_learnings_summary() -> a human-readable digest of what the agent learned.

Pure stdlib + the existing memory.py sqlite layer. No network, no LLM.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from typing import Optional

import memory
from models import VALID_STAGES
from scoring_v7 import V7_WEIGHTS

# Outcome vocabulary. Positive = the deal advanced/converted; negative = it died.
POSITIVE_OUTCOMES = {"LOI", "closed"}
NEGATIVE_OUTCOMES = {"passed", "withdrew", "passed_on"}
VALID_OUTCOMES = sorted(POSITIVE_OUTCOMES | NEGATIVE_OUTCOMES)

# Where reviewed, applied weight deltas are persisted for scoring_v7 to read.
LEARNED_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "learned_weights.json")

# How aggressively a full 0<->100 dimension separation nudges a weight.
# A dimension that perfectly separates winners from losers proposes at most
# +MAX_WEIGHT_DELTA to its weight (renormalised downstream by resolve_weights).
MAX_WEIGHT_DELTA = 0.03

# Overall-score threshold above which a deal is considered "high-scored".
HIGH_SCORE_THRESHOLD = 6.5

# Map each V7_WEIGHTS axis -> (deal score field, inverted?). Inverted axes store a
# raw risk where HIGHER = WORSE, so we flip to (100 - raw) for correlation, keeping
# "higher is better" consistent across every dimension.
_AXIS_TO_FIELD: dict[str, tuple[str, bool]] = {
    "cashflow": ("cashflow_score", False),
    "profit_potential": ("profit_potential_score", False),
    "exit_potential": ("exit_potential_score", False),
    "moat": ("moat_score", False),
    "tam": ("tam_score", False),
    "competitor_analysis": ("competitor_analysis_score", False),
    "ai_proof": ("ai_proof_score", False),
    "company_life": ("company_life_score", False),
    "buy_vs_build": ("buy_vs_build_score", False),        # 0-10 scale; scaled below
    "mitigation": ("mitigation_score", False),
    "owner_neglect_inverted": ("owner_neglect_score", True),
    "platform_risk_inverted": ("platform_dependency_risk_score", True),
    "risk_inverted": ("risk_score", True),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# RECORD
# ===========================================================================

def record_outcome(
    deal_id: str,
    stage: str,
    outcome: str,
    notes: str = "",
    weight_delta: Optional[dict] = None,
    db_path: str = memory.DB_PATH,
) -> str:
    """Append a deal outcome to the learnings table. Returns the learning id.

    `stage` must be one of VALID_STAGES; `outcome` one of VALID_OUTCOMES. `notes`
    is stored as the free-text lesson.
    """
    if stage not in VALID_STAGES:
        raise ValueError(f"stage {stage!r} not in VALID_STAGES {VALID_STAGES}")
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome {outcome!r} not in VALID_OUTCOMES {VALID_OUTCOMES}")
    memory.init_db(db_path)
    return memory.record_learning(
        deal_id=deal_id, stage=stage, outcome=outcome,
        lesson=notes, weight_delta=weight_delta, path=db_path,
    )


# ===========================================================================
# RECALIBRATE (propose, never mutate)
# ===========================================================================

def _dimension_value(score_json: dict, axis: str) -> Optional[float]:
    """Extract the 'higher = better' dimension value for an axis from a deal blob."""
    field, inverted = _AXIS_TO_FIELD[axis]
    raw = score_json.get(field)
    if raw is None:
        return None
    val = float(raw)
    if axis == "buy_vs_build":       # stored 0-10, normalise to 0-100
        val *= 10.0
    return (100.0 - val) if inverted else val


def recalibrate(db_path: str = memory.DB_PATH, log_proposal: bool = True) -> dict:
    """Correlate each scoring dimension with outcomes and PROPOSE weight deltas.

    For each dimension: mean('higher=better' value) over deals with a POSITIVE
    outcome minus the mean over deals with a NEGATIVE outcome. A positive
    separation means the dimension was higher for winners -> propose increasing
    its weight; negative -> propose decreasing it. Delta is scaled by
    MAX_WEIGHT_DELTA / 100 and clamped so a single round can only nudge gently.

    Returns a proposal dict. Does NOT modify V7_WEIGHTS or the learned-weights
    file. When `log_proposal`, the proposal is appended to `directive_versions`
    as a `proposed-*` version so a human/agent can review before apply_learning().
    """
    learnings = memory.list_learnings(path=db_path)

    pos_vals: dict[str, list] = {axis: [] for axis in _AXIS_TO_FIELD}
    neg_vals: dict[str, list] = {axis: [] for axis in _AXIS_TO_FIELD}
    n_pos = n_neg = n_missing = 0

    for lrn in learnings:
        outcome = lrn.get("outcome", "")
        if outcome in POSITIVE_OUTCOMES:
            bucket = pos_vals
            n_pos += 1
        elif outcome in NEGATIVE_OUTCOMES:
            bucket = neg_vals
            n_neg += 1
        else:
            continue

        stored = memory.get_deal(lrn.get("deal_id", ""), path=db_path)
        if not stored:
            n_missing += 1
            continue
        for axis in _AXIS_TO_FIELD:
            val = _dimension_value(stored, axis)
            if val is not None:
                bucket[axis].append(val)

    proposed_deltas: dict[str, float] = {}
    dimension_report: dict[str, dict] = {}
    for axis in _AXIS_TO_FIELD:
        p, n = pos_vals[axis], neg_vals[axis]
        if not p or not n:
            continue
        mean_pos = statistics.fmean(p)
        mean_neg = statistics.fmean(n)
        separation = mean_pos - mean_neg               # -100 .. 100
        delta = round((separation / 100.0) * MAX_WEIGHT_DELTA, 5)
        delta = max(-MAX_WEIGHT_DELTA, min(MAX_WEIGHT_DELTA, delta))
        proposed_deltas[axis] = delta
        dimension_report[axis] = {
            "mean_positive": round(mean_pos, 2),
            "mean_negative": round(mean_neg, 2),
            "separation": round(separation, 2),
            "proposed_weight_delta": delta,
            "current_weight": V7_WEIGHTS[axis],
            "proposed_weight": round(max(0.0, V7_WEIGHTS[axis] + delta), 5),
        }

    proposal = {
        "kind": "weight_recalibration_proposal",
        "created_at": _now(),
        "n_learnings": len(learnings),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_deals_missing_scores": n_missing,
        "proposed_deltas": proposed_deltas,
        "dimension_report": dimension_report,
        "note": (
            "PROPOSAL ONLY — base weights are NOT mutated. Review, then call "
            "apply_learning(proposed_deltas) to persist an override."
        ),
    }

    if log_proposal and proposed_deltas:
        version = f"proposed-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        memory.save_directive_version(
            version=version, content=json.dumps(proposal, indent=2), path=db_path,
        )
        proposal["logged_version"] = version

    return proposal


# ===========================================================================
# APPLY (persist reviewed deltas into the scoring override)
# ===========================================================================

def load_learned_weights(path: str = LEARNED_WEIGHTS_PATH) -> dict:
    """Load the current LEARNED_WEIGHTS override (absolute weights), or {} if none."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_learning(
    dimension_weights_delta: dict,
    weights_path: str = LEARNED_WEIGHTS_PATH,
    db_path: str = memory.DB_PATH,
) -> dict:
    """Apply REVIEWED weight deltas to the LEARNED_WEIGHTS override.

    Starts from any existing override (or the V7 base), adds the deltas, floors
    at 0, and writes an absolute {axis: weight} table to `weights_path`. That
    file is what analyze_deal_v7(weights_override=...) consumes. The application
    is logged to `directive_versions` as an `applied-*` version.

    Unknown axes in the delta are ignored. Returns the resulting absolute weights.
    """
    base = load_learned_weights(weights_path) or dict(V7_WEIGHTS)
    applied: dict[str, float] = dict(base)
    for axis, delta in dimension_weights_delta.items():
        if axis in V7_WEIGHTS:
            applied[axis] = round(max(0.0, applied.get(axis, V7_WEIGHTS[axis]) + float(delta)), 5)

    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(applied, fh, indent=2)

    memory.init_db(db_path)
    version = f"applied-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    memory.save_directive_version(
        version=version,
        content=json.dumps(
            {"kind": "weight_override_applied", "applied_deltas": dimension_weights_delta,
             "resulting_weights": applied, "applied_at": _now()},
            indent=2,
        ),
        path=db_path,
    )
    return applied


# ===========================================================================
# SUMMARY
# ===========================================================================

def get_learnings_summary(db_path: str = memory.DB_PATH) -> dict:
    """Digest of what the agent has learned: counts, top lessons, and the
    high-score -> conversion correlation.

    high_score_precision: of deals scored >= HIGH_SCORE_THRESHOLD, the fraction
    that had a POSITIVE outcome (does a high score actually predict conversion?).
    """
    learnings = memory.list_learnings(path=db_path)

    outcome_counts: dict[str, int] = {}
    deal_ids: set = set()
    pos_scores: list = []
    neg_scores: list = []
    high_pos = high_total = 0
    top_lessons: list = []

    for lrn in learnings:
        outcome = lrn.get("outcome", "")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        deal_ids.add(lrn.get("deal_id", ""))
        if lrn.get("lesson"):
            top_lessons.append({"outcome": outcome, "lesson": lrn["lesson"]})

        stored = memory.get_deal(lrn.get("deal_id", ""), path=db_path)
        if not stored:
            continue
        score = float(stored.get("overall_score", 0.0))
        is_positive = outcome in POSITIVE_OUTCOMES
        (pos_scores if is_positive else neg_scores).append(score)
        if score >= HIGH_SCORE_THRESHOLD:
            high_total += 1
            if is_positive:
                high_pos += 1

    return {
        "n_learnings": len(learnings),
        "n_deals": len(deal_ids - {""}),
        "outcome_counts": outcome_counts,
        "mean_score_positive": round(statistics.fmean(pos_scores), 2) if pos_scores else None,
        "mean_score_negative": round(statistics.fmean(neg_scores), 2) if neg_scores else None,
        "high_score_threshold": HIGH_SCORE_THRESHOLD,
        "high_score_precision": round(high_pos / high_total, 3) if high_total else None,
        "high_score_n": high_total,
        "top_lessons": top_lessons[:5],
        "learned_weights_active": bool(load_learned_weights()),
    }
