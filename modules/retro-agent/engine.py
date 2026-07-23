"""
EVA Retro-Agent — pure weekly-retrospective engine (no I/O, no network).

Given the raw eva-state events read for the retro window and last week's stated
course-correction priorities, this computes the Weekly Retro Digest
deterministically. No LLM, no clock surprises: same inputs → same digest. The
optional brain (``brain.py``) only sharpens the narrative prose afterwards — it
never changes a status, a flag, or a count.

No-circularity rule (mirrors activity-tracker-agent / trend-agent): every
shipped item, pipeline movement, stale blocker, and "priority worked on?" verdict
is derived from events actually read — never asserted first. A window with zero
events read is reported as a verification gap, not a clean/ON_TRACK week.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from models import (
    BLOCKER_EVENT_TYPES,
    BLOCKER_STATUSES,
    REVENUE_EVENT_TYPES,
    REVENUE_PAYLOAD_KEYS,
    REVENUE_WIN_STAGES,
    RESOLVED_EVENT_TYPES,
    SHIPPED_EVENT_TYPES,
    STALE_AFTER_DAYS,
    STATUS_DRIFTING,
    STATUS_ON_TRACK,
    STATUS_REVENUE_WIN,
    STATUS_STALLED_BLOCKER,
    PipelineMovement,
    PriorityCheck,
    RetroDigest,
    ShippedItem,
    StaleBlocker,
)

# tokens too generic to count as evidence a priority was worked on.
_STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "that", "this", "week",
    "eva", "get", "make", "ship", "build", "work", "close", "first", "next",
    "more", "less", "than", "over", "onto", "via", "our", "its", "was", "are",
    "priority", "priorities", "course", "correction", "task", "tasks",
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _revenue_amount(event: dict) -> Optional[float]:
    payload = event.get("payload") or {}
    for key in REVENUE_PAYLOAD_KEYS:
        val = payload.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    return None


def _entity_key(event: dict) -> str:
    payload = event.get("payload") or {}
    return str(
        event.get("entity_id")
        or payload.get("name")
        or payload.get("pipeline")
        or event.get("summary")
        or "unnamed"
    )


def _shipped_kind(event_type: str) -> str:
    if "module" in event_type:
        return "module"
    if "catalog" in event_type:
        return "catalog"
    if "commit" in event_type:
        return "commit"
    if "deploy" in event_type:
        return "deploy"
    if "pr_" in event_type:
        return "pull_request"
    return "build"


def _tokens(text: str) -> set[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in (text or ""))
    return {t for t in cleaned.split() if len(t) >= 4 and t not in _STOPWORDS}


def _in_window(ts: Optional[str], start: date, end: date) -> bool:
    d = _parse_date(ts)
    return d is not None and start <= d <= end


def build_retro(
    events: list[dict],
    *,
    week_start: str,
    week_end: str,
    prior_priorities: Optional[list[str]] = None,
    prior_priorities_source: str = "",
) -> RetroDigest:
    """Compute the Weekly Retro Digest.

    ``events`` may span wider than the 7-day window (blockers are tracked across
    their whole open lifetime); shipping/pipeline/priority evidence only counts
    events dated within [week_start, week_end].
    """
    prior_priorities = [p for p in (prior_priorities or []) if p and p.strip()]
    start_d = _parse_date(week_start) or date.min
    end_d = _parse_date(week_end) or date.max

    recent = [e for e in events if _in_window(e.get("timestamp"), start_d, end_d)]

    # --- (a) what shipped ---------------------------------------------------
    shipped: list[ShippedItem] = []
    for e in recent:
        et = e.get("event_type") or ""
        if et in SHIPPED_EVENT_TYPES:
            payload = e.get("payload") or {}
            shipped.append(ShippedItem(
                kind=_shipped_kind(et),
                name=str(payload.get("name") or e.get("entity_id") or e.get("summary") or et),
                event_type=et,
                summary=e.get("summary") or "",
                timestamp=e.get("timestamp"),
            ))

    # --- (b) revenue-pipeline movement --------------------------------------
    movements: list[PipelineMovement] = []
    for e in recent:
        et = e.get("event_type") or ""
        payload = e.get("payload") or {}
        amount = _revenue_amount(e)
        to_stage = str(payload.get("to_stage") or payload.get("stage") or "")
        is_stage_change = et == "pipeline_stage_changed" or bool(payload.get("to_stage"))
        is_revenue_event = et in REVENUE_EVENT_TYPES or amount is not None
        if not (is_stage_change or is_revenue_event):
            continue
        win = (
            is_revenue_event
            or any(w in to_stage.lower() for w in REVENUE_WIN_STAGES)
        )
        movements.append(PipelineMovement(
            pipeline=str(payload.get("pipeline") or e.get("entity_id") or e.get("summary") or "pipeline"),
            from_stage=payload.get("from_stage"),
            to_stage=to_stage or None,
            is_revenue_win=win,
            amount=amount,
            summary=e.get("summary") or "",
            timestamp=e.get("timestamp"),
        ))
    revenue_movements = [m for m in movements if m.is_revenue_win]

    # --- (c) stale blockers (tracked across full lifetime) ------------------
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        et = e.get("event_type") or ""
        status = str((e.get("payload") or {}).get("status") or "").lower()
        if et in BLOCKER_EVENT_TYPES or status in BLOCKER_STATUSES:
            by_entity[_entity_key(e)].append(e)

    stale: list[StaleBlocker] = []
    for key, evs in by_entity.items():
        evs_sorted = sorted(evs, key=lambda x: str(x.get("timestamp") or ""))
        latest = evs_sorted[-1]
        # If any RESOLVING event happened after the latest blocker event, skip.
        latest_ts = _parse_date(latest.get("timestamp"))
        resolved_after = any(
            (e.get("event_type") in RESOLVED_EVENT_TYPES)
            and (_parse_date(e.get("timestamp")) or date.min) >= (latest_ts or date.min)
            for e in events if _entity_key(e) == key
        )
        if resolved_after:
            continue
        age = (end_d - latest_ts).days if latest_ts else 0
        if age > STALE_AFTER_DAYS:
            status = str((latest.get("payload") or {}).get("status") or latest.get("event_type") or "pending")
            stale.append(StaleBlocker(
                name=key,
                status=status,
                last_movement=latest.get("timestamp"),
                age_days=age,
                summary=latest.get("summary") or "",
            ))
    stale.sort(key=lambda b: -b.age_days)

    # --- (d) were last week's priorities worked on? -------------------------
    evidence_tokens: dict[str, str] = {}
    for item in shipped:
        for tok in _tokens(f"{item.name} {item.summary}"):
            evidence_tokens.setdefault(tok, f"shipped: {item.name}")
    for m in movements:
        for tok in _tokens(f"{m.pipeline} {m.summary} {m.to_stage or ''}"):
            evidence_tokens.setdefault(tok, f"pipeline moved: {m.pipeline}")

    priority_checks: list[PriorityCheck] = []
    for p in prior_priorities:
        hit = next((evidence_tokens[t] for t in _tokens(p) if t in evidence_tokens), "")
        priority_checks.append(PriorityCheck(priority=p, addressed=bool(hit), evidence=hit))
    addressed = sum(1 for c in priority_checks if c.addressed)

    # --- roll-up: notes, drift, status --------------------------------------
    notes: list[str] = []
    drift_note: Optional[str] = None

    if not events:
        notes.append(
            "No eva-state events read for the retro window — cannot verify what "
            "shipped or moved. Treat as a logging gap, not a clean week."
        )
    if revenue_movements:
        wins = ", ".join(sorted({m.pipeline for m in revenue_movements}))
        notes.append(
            f"Revenue-pipeline movement this week: {wins}. This is the $10K/month "
            f"critical path — protect and double down on whatever produced it."
        )
    if stale:
        top = stale[0]
        notes.append(
            f"{len(stale)} blocker(s) pending > {STALE_AFTER_DAYS} days without "
            f"movement — oldest: '{top.name}' ({top.age_days}d, {top.status}). "
            f"Unstick or kill these before starting new infra."
        )
    if prior_priorities and addressed < len(prior_priorities):
        unaddressed = [c.priority for c in priority_checks if not c.addressed]
        notes.append(
            f"Only {addressed}/{len(prior_priorities)} of last week's stated "
            f"course-correction priorities show any movement this week. No evidence "
            f"for: {'; '.join(unaddressed)}."
        )

    # Drift = built infra but no revenue-pipeline advanced.
    if shipped and not revenue_movements:
        drift_note = (
            f"{len(shipped)} build/churn event(s) shipped this week but ZERO "
            f"revenue-pipeline rows advanced — infra work is outpacing revenue work. "
            f"Reallocate next week toward actions that move a pipeline stage."
        )
        notes.append(drift_note)

    # status ladder (precedence: REVENUE_WIN > STALLED_BLOCKER > DRIFTING > ON_TRACK)
    if revenue_movements:
        status = STATUS_REVENUE_WIN
    elif stale:
        status = STATUS_STALLED_BLOCKER
    elif drift_note or not events:
        status = STATUS_DRIFTING
    else:
        status = STATUS_ON_TRACK

    if status == STATUS_ON_TRACK and not notes:
        notes.append(
            "No revenue-pipeline movement, no stale blockers, and prior priorities "
            "were touched. Steady — keep pushing on the revenue path."
        )

    narrative = _render_narrative(
        week_start, week_end, status, shipped, movements, stale,
        priority_checks, notes,
    )

    return RetroDigest(
        week_start=week_start,
        week_end=week_end,
        status=status,
        revenue_win=bool(revenue_movements),
        shipped=shipped,
        pipeline_movements=movements,
        stale_blockers=stale,
        priority_checks=priority_checks,
        prior_priorities_source=prior_priorities_source,
        shipped_count=len(shipped),
        revenue_movement_count=len(revenue_movements),
        priorities_addressed=addressed,
        priorities_total=len(prior_priorities),
        drift_note=drift_note,
        course_correction_notes=notes,
        narrative=narrative,
    )


def _render_narrative(
    week_start: str, week_end: str, status: str,
    shipped: list[ShippedItem], movements: list[PipelineMovement],
    stale: list[StaleBlocker], priority_checks: list[PriorityCheck],
    notes: list[str],
) -> str:
    """Deterministic plain-text digest. The brain may sharpen this prose later."""
    lines = [
        f"EVA WEEKLY RETRO — {week_start} → {week_end}",
        f"STATUS: {status}",
        "",
        f"Shipped (infra/churn): {len(shipped)} event(s)"
        + (f" — {', '.join(s.name for s in shipped[:6])}" if shipped else ""),
        f"Revenue-pipeline movement: {len([m for m in movements if m.is_revenue_win])} win(s)"
        + (f" — {', '.join(m.pipeline for m in movements if m.is_revenue_win)}"
           if any(m.is_revenue_win for m in movements) else " — none"),
        f"Stale blockers (> {STALE_AFTER_DAYS}d): {len(stale)}"
        + (f" — {', '.join(f'{b.name} ({b.age_days}d)' for b in stale[:5])}" if stale else ""),
    ]
    if priority_checks:
        done = sum(1 for c in priority_checks if c.addressed)
        lines.append(f"Prior priorities worked on: {done}/{len(priority_checks)}")
        for c in priority_checks:
            mark = "✓" if c.addressed else "✗"
            lines.append(f"  {mark} {c.priority}" + (f"  [{c.evidence}]" if c.evidence else ""))
    lines.append("")
    lines.append("Course-correction:")
    for n in notes:
        lines.append(f"  • {n}")
    return "\n".join(lines)


__all__ = ["build_retro", "STALE_AFTER_DAYS"]
