"""
EVA Idea-Generator-Agent — daily alignment / red-flag digest.

Answers one question every day: is Eva's actual activity still converging on
the goal (Storeys RE PE fund + Mangotec AI-agency revenue), or has it drifted
into off-thesis busywork? Reads the eva-state ledger (the one shared timeline
every module already writes to — this is the "Spain soccer team" sync
surface, not a new one), buckets events by ``track`` over a trailing window,
and raises a RED_FLAG when goal-aligned activity share falls too low or when
too many low-synergy BUILD calls went out unchecked.

Deterministic, no LLM. Mirrors trend-agent/deal-financing-agent's
no-circularity rule: the status is computed from the ledger, never assumed.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from models import GOAL_TRACKS, AlignmentDigest

GOAL_SHARE_RED_FLAG = 0.35    # below this fraction of activity in GOAL_TRACKS -> red flag
GOAL_SHARE_WATCH = 0.50       # below this -> watch
LOW_SYNERGY_BUILD_RED_FLAG = 3  # this many low-synergy BUILD/PARTNER calls in window -> red flag


def build_digest(events: list[dict], *, window_days: int = 7) -> AlignmentDigest:
    """``events`` are raw eva-state event dicts (must include ``track`` where
    known; events with no track are counted as off-thesis — unlabeled work is
    not assumed aligned)."""
    total = len(events)
    track_counts = Counter((e.get("track") or "unlabeled") for e in events)
    goal_count = sum(track_counts.get(t, 0) for t in GOAL_TRACKS)
    goal_share = round(goal_count / total, 3) if total else 1.0
    off_share = round(1 - goal_share, 3)

    low_synergy_builds = sum(
        1 for e in events
        if (e.get("event_type") == "idea_scored")
        and (e.get("payload") or {}).get("recommendation") in ("BUILD", "PARTNER")
        and (e.get("payload") or {}).get("sub_scores", {}).get("portfolio_synergy_score", 10) < 6
    )

    red_flags: list[str] = []
    status = "OK"

    if total == 0:
        red_flags.append("No eva-state activity in window — cannot verify alignment; "
                          "treat as a gap, not a clean signal.")
        status = "WATCH"
    elif goal_share < GOAL_SHARE_RED_FLAG:
        red_flags.append(
            f"Only {goal_share:.0%} of the last {window_days}d of activity is "
            f"in goal tracks ({', '.join(GOAL_TRACKS)}) — majority of effort is "
            f"off-thesis. RED FLAG.")
        status = "RED_FLAG"
    elif goal_share < GOAL_SHARE_WATCH:
        red_flags.append(
            f"Goal-track share is {goal_share:.0%}, below the {GOAL_SHARE_WATCH:.0%} "
            f"watch line — trending off-thesis, not yet a red flag.")
        status = "WATCH"

    if low_synergy_builds >= LOW_SYNERGY_BUILD_RED_FLAG:
        red_flags.append(
            f"{low_synergy_builds} BUILD/PARTNER calls in window scored low "
            f"portfolio synergy (<6) — pattern of chasing ideas that don't "
            f"leverage what we already operate. RED FLAG.")
        status = "RED_FLAG"

    return AlignmentDigest(
        window_days=window_days,
        total_events=total,
        goal_track_share=goal_share,
        off_thesis_share=off_share,
        recent_low_synergy_builds=low_synergy_builds,
        red_flags=red_flags,
        status=status,
    )


__all__ = ["build_digest", "GOAL_SHARE_RED_FLAG", "GOAL_SHARE_WATCH"]
