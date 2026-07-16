"""
EVA IP-Scout — Eva-activity mining (v1 stub).

The second sensor (alongside user-seeded ideas): mine the eva-state event ledger
for REPEATABLE / NOVEL process patterns that Eva itself runs — a process an
operator repeats often enough, or a distinctive multi-step workflow, can be an
invention disclosure candidate ("a method for ...").

v1 is a deterministic STUB: it groups events by ``event_type`` and surfaces the
ones that recur at or above a threshold as candidate idea seeds. It does NOT do
NLP/embedding clustering — that's a phase-2 upgrade behind this same interface.
Every mined candidate is clearly tagged ``sensor_source = "activity-mining"`` so
downstream triage/attorney-review treats it as machine-proposed.
"""

from __future__ import annotations

from collections import Counter

# Ledger noise we never want to propose as an invention.
_IGNORED_EVENT_TYPES = {
    "heartbeat", "health_check", "status", "log", "error",
    # IP-Scout's own events — never mine ourselves.
    "ip_idea_seeded", "ip_scan_run", "ip_disclosure_created", "ip_report_written",
}

DEFAULT_MIN_OCCURRENCES = 3


def mine_activity(events: list[dict], *, min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
                  known_idea_ids: set[str] | None = None) -> list[dict]:
    """Return candidate idea seeds mined from eva-state events.

    A candidate is an ``event_type`` that recurs ``>= min_occurrences`` times
    (a repeatable process worth a disclosure look). Each candidate is shaped like
    a user-seeded idea record so it flows through the same triage path.
    """
    known_idea_ids = known_idea_ids or set()
    counts: Counter = Counter()
    exemplar: dict[str, dict] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        et = (ev.get("event_type") or "").strip()
        if not et or et in _IGNORED_EVENT_TYPES:
            continue
        counts[et] += 1
        exemplar.setdefault(et, ev)

    candidates = []
    for et, n in counts.items():
        if n < min_occurrences:
            continue
        idea_id = f"mined-{et}"
        if idea_id in known_idea_ids:
            continue
        ex = exemplar.get(et, {})
        surface = ex.get("source_surface", "eva")
        candidates.append({
            "id": idea_id,
            "title": f"Automated process: {et.replace('_', ' ')}",
            "description": (
                f"Eva repeatedly runs a '{et}' process ({n} occurrences observed "
                f"via {surface}). A repeatable multi-step automated workflow may be "
                f"a novel method worth an attorney's review as an invention "
                f"disclosure. Example summary: {ex.get('summary', '')[:160]}"
            ),
            "category": "process-automation",
            "sensor_source": "activity-mining",
            "occurrences": n,
        })

    candidates.sort(key=lambda c: c["occurrences"], reverse=True)
    return candidates


__all__ = ["mine_activity", "DEFAULT_MIN_OCCURRENCES"]
