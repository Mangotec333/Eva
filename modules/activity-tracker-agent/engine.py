"""
EVA Activity-Tracker-Agent — pure digest engine (no I/O, no network).

Answers, every day: where did the time/effort actually go, is any of it
revenue traction worth doubling down on, and what should change tomorrow.
Deterministic, no LLM — mirrors trend-agent / idea-generator-agent's
no-circularity rule: the digest is computed from the day's events, never
assumed going in.

Effort proxy: event_count per project. This is explicit and intentional —
this module has no real time-tracking input yet (context-api's raw
screen/calendar activity is a future upgrade path, see directive.md). Never
call this "hours" or "minutes" anywhere in output.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from models import (
    GOAL_TRACKS,
    REVENUE_EVENT_TYPES,
    STATUS_DOUBLE_DOWN,
    STATUS_OK,
    STATUS_RED_FLAG,
    STATUS_WATCH,
    ActivityBucket,
    DailyDigest,
    PatternFlag,
    RevenueTractionSignal,
)

# Event types that indicate something is stuck, not just busy.
BLOCKER_EVENT_TYPES = {
    "task_stalled",
    "revenue_leak_found",
    "local_exec_blocked",
    "deploy_failed",
    "local_exec_denied",
}
RECURRING_BLOCKER_MIN = 2      # same project, this many blocker-shaped events today
LOW_LEVERAGE_MIN_EVENTS = 5    # busy, but ...
GOAL_SHARE_RED_FLAG = 0.35     # mirrors idea-generator-agent's threshold

# payload keys checked (in order) for a numeric revenue amount, on top of
# REVENUE_EVENT_TYPES matches (an event can be revenue-shaped without one of
# those exact event_type values, e.g. a custom payload.revenue_amount).
REVENUE_PAYLOAD_KEYS = ("revenue_amount", "amount", "deal_amount", "mrr_delta", "payment_amount")


def _revenue_amount(event: dict) -> Optional[float]:
    payload = event.get("payload") or {}
    for key in REVENUE_PAYLOAD_KEYS:
        val = payload.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    return None


def _is_revenue_event(event: dict) -> bool:
    if event.get("event_type") in REVENUE_EVENT_TYPES:
        return True
    return _revenue_amount(event) is not None


def build_digest(events: list[dict], *, date: str) -> DailyDigest:
    """``events`` are raw eva-state event dicts for the single day ``date``
    covers. Events with no ``project`` are bucketed as "unlabeled" — unlabeled
    work is not assumed aligned or wasted, just uncategorized."""
    total = len(events)
    by_project: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_project[e.get("project") or "unlabeled"].append(e)

    track_counts = Counter((e.get("track") or "unlabeled") for e in events)
    goal_count = sum(track_counts.get(t, 0) for t in GOAL_TRACKS)
    goal_share = round(goal_count / total, 3) if total else 0.0

    buckets: list[ActivityBucket] = []
    patterns: list[PatternFlag] = []
    revenue_signals: list[RevenueTractionSignal] = []
    high_leverage: list[str] = []
    low_leverage: list[str] = []

    for project, evs in sorted(by_project.items(), key=lambda kv: -len(kv[1])):
        type_counts = Counter(e.get("event_type") or "unknown" for e in evs)
        timestamps = sorted(e.get("timestamp") for e in evs if e.get("timestamp"))
        track = next((e.get("track") for e in evs if e.get("track")), None)

        rev_events = [e for e in evs if _is_revenue_event(e)]
        rev_sum = sum((_revenue_amount(e) or 0.0) for e in rev_events)

        bucket = ActivityBucket(
            project=project,
            track=track,
            event_count=len(evs),
            event_types=dict(type_counts),
            has_revenue_signal=bool(rev_events),
            revenue_amount_sum=rev_sum,
            first_seen=timestamps[0] if timestamps else None,
            last_seen=timestamps[-1] if timestamps else None,
        )
        buckets.append(bucket)

        for e in rev_events:
            revenue_signals.append(RevenueTractionSignal(
                project=project,
                event_type=e.get("event_type") or "unknown",
                amount=_revenue_amount(e),
                summary=e.get("summary") or "",
                entity_id=e.get("entity_id"),
            ))

        blocker_count = sum(type_counts.get(t, 0) for t in BLOCKER_EVENT_TYPES)
        if blocker_count >= RECURRING_BLOCKER_MIN:
            patterns.append(PatternFlag(
                kind="recurring_blocker",
                project=project,
                description=(
                    f"{blocker_count} blocker-shaped events today "
                    f"({', '.join(t for t in BLOCKER_EVENT_TYPES if type_counts.get(t))}) "
                    f"— this project is stuck, not just slow."
                ),
                evidence_count=blocker_count,
            ))
        elif type_counts.get("task_stalled"):
            patterns.append(PatternFlag(
                kind="stalled_thread",
                project=project,
                description=f"{type_counts['task_stalled']} stalled-task event(s) today.",
                evidence_count=type_counts["task_stalled"],
            ))

        if bucket.has_revenue_signal:
            high_leverage.append(project)
            patterns.append(PatternFlag(
                kind="high_leverage",
                project=project,
                description=(
                    f"Revenue-side event logged (${rev_sum:,.0f} tracked) — "
                    f"highest-leverage project today."
                ),
                evidence_count=len(rev_events),
            ))
        elif bucket.event_count >= LOW_LEVERAGE_MIN_EVENTS:
            low_leverage.append(project)
            patterns.append(PatternFlag(
                kind="low_leverage",
                project=project,
                description=(
                    f"{bucket.event_count} events today, zero revenue signal — "
                    f"high activity, no movement on revenue > 0. Reassess before "
                    f"committing more time tomorrow."
                ),
                evidence_count=bucket.event_count,
            ))

    course_correction_notes: list[str] = []
    double_down_recommendation: Optional[str] = None

    if revenue_signals:
        projects_str = ", ".join(sorted({r.project for r in revenue_signals}))
        double_down_recommendation = (
            f"Revenue traction detected in: {projects_str}. Leave lower-leverage "
            f"work behind, reallocate time here first, and arrange a team around "
            f"it based on what it needs to scale."
        )
        course_correction_notes.append(double_down_recommendation)

    if low_leverage:
        course_correction_notes.append(
            f"High-activity / zero-revenue today: {', '.join(low_leverage)}. "
            f"Cut, delegate, or timebox these before adding more effort."
        )

    if total == 0:
        course_correction_notes.append(
            "No eva-state activity logged today — cannot verify where time went. "
            "Treat this as a logging gap, not a clean signal."
        )
    elif goal_share < GOAL_SHARE_RED_FLAG:
        course_correction_notes.append(
            f"Only {goal_share:.0%} of today's logged activity is in goal tracks "
            f"({', '.join(GOAL_TRACKS)}) — majority of the day drifted off-thesis."
        )

    if not revenue_signals and not course_correction_notes:
        course_correction_notes.append(
            "No revenue-side event logged today. Tomorrow's plan should skew "
            "toward actions that can produce one."
        )

    if revenue_signals:
        status = STATUS_DOUBLE_DOWN
    elif total == 0 or goal_share < GOAL_SHARE_RED_FLAG:
        status = STATUS_RED_FLAG
    elif low_leverage:
        status = STATUS_WATCH
    else:
        status = STATUS_OK

    return DailyDigest(
        date=date,
        total_events=total,
        buckets=buckets,
        patterns=patterns,
        revenue_signals=revenue_signals,
        goal_track_share=goal_share,
        high_leverage_projects=high_leverage,
        low_leverage_projects=low_leverage,
        double_down_recommendation=double_down_recommendation,
        course_correction_notes=course_correction_notes,
        status=status,
    )


__all__ = ["build_digest", "GOAL_SHARE_RED_FLAG", "LOW_LEVERAGE_MIN_EVENTS", "RECURRING_BLOCKER_MIN"]
