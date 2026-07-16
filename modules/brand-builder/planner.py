"""
EVA Brand-Builder — weekly content-plan generator (blueprint + personas → briefs).

The planner is the whole point of the Brand Builder: given a pipeline and its
blueprint, it produces a weekly plan of content BRIEFS (never posts). Each brief
is a strategic instruction for content-engine (:8767) to draft against, carrying
the channel, archetype, persona, hook, angle, CTA, proof asset, voice rules and
do-not-say guardrails — everything content-engine needs to write on-brand copy.

Cadence comes straight from the blueprint's section-7 table (Daily X, 3x/week
LinkedIn, weekly newsletter, …). Generation is deterministic (round-robin over
archetypes + days, no randomness) so plans are reproducible and testable offline.
Stdlib only (re, datetime, uuid).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

import personas as personas_mod
import store


def weekly_count(cadence_text: str) -> int:
    """Map a cadence phrase to how many posts it implies in one week."""
    t = (cadence_text or "").lower()
    if "daily" in t or "1 post/day" in t:
        return 7
    m = re.search(r"(\d+)\s*[x×]\s*/\s*week", t)
    if m:
        return int(m.group(1))
    if "weekly" in t or "1x/week" in t or "at least weekly" in t:
        return 1
    if "/month" in t or "quarter" in t:
        return 0  # too infrequent to land in a single-week plan
    return 0


def _channel_slots(cadence: dict) -> list[str]:
    """Flatten cadence into an ordered list of channel slots for one week."""
    slots: list[str] = []
    # Stable priority order so plans are deterministic.
    priority = ["X (Twitter)", "LinkedIn", "Newsletter", "Conversion posts (LinkedIn)"]
    ordered = [c for c in priority if c in cadence] + \
              [c for c in cadence if c not in priority]
    for channel in ordered:
        n = weekly_count(cadence.get(channel, ""))
        slots.extend([channel] * n)
    return slots


def _archetypes_for_channel(channel: str, blueprint: dict) -> list[str]:
    """Pick blueprint archetypes appropriate to a channel."""
    all_arch = [a["name"] for a in blueprint.get("content_archetypes", [])] or [
        "Deal Teardowns", "Data/Proof Posts", "Build-in-Public"]
    ch = channel.lower()
    if "newsletter" in ch:
        return [a for a in all_arch if a in ("Data/Proof Posts", "Frameworks", "Contrarian Thesis")] or all_arch
    if ch.startswith("x") or "twitter" in ch:
        return [a for a in all_arch if a in ("Deal Teardowns", "Contrarian Thesis", "Build-in-Public")] or all_arch
    return all_arch


def _hook_for(archetype: str, persona: dict, blueprint: dict) -> str:
    """Best hook: an awareness-loop hook matching the archetype, else persona hook."""
    a = archetype.lower()
    for loop in blueprint.get("awareness_loops", []):
        name = (loop.get("name", "") + loop.get("hook", "")).lower()
        if archetype.split()[0].lower() in name and loop.get("hook"):
            return loop["hook"]
    hooks = persona.get("hooks") or []
    return hooks[0] if hooks else f"{archetype}: lead with a specific, data-backed observation."


def generate_plan(pipeline: dict, blueprint: dict, persona_map: dict,
                  *, timeframe: str = "week", start_date: str | None = None) -> list[dict]:
    """Produce a list of brief dicts for the given timeframe (default one week)."""
    weeks = _timeframe_weeks(timeframe)
    cadence = blueprint.get("cadence", {}) or {}
    slots = _channel_slots(cadence)
    if not slots:  # blueprint had no usable cadence — safe fallback
        slots = ["X (Twitter)"] * 7 + ["LinkedIn"] * 3 + ["Newsletter"]

    start = _parse_date(start_date) or date.today()
    proof_assets = pipeline.get("proof_assets") or []
    briefs: list[dict] = []
    counters: dict[str, int] = {}

    for week in range(weeks):
        # Spread each channel's slots across the 7 days deterministically.
        day_cursor: dict[str, int] = {}
        per_channel: dict[str, int] = {}
        for ch in slots:
            per_channel[ch] = per_channel.get(ch, 0) + 1
        for i, channel in enumerate(slots):
            arch_list = _archetypes_for_channel(channel, blueprint)
            ci = counters.get(channel, 0)
            archetype = arch_list[ci % len(arch_list)]
            counters[channel] = ci + 1

            persona_name = personas_mod.select_persona(archetype)
            persona = persona_map.get(persona_name, {})

            # even spread of this channel's posts over 7 days
            total_ch = per_channel[channel]
            slot_idx = day_cursor.get(channel, 0)
            day_cursor[channel] = slot_idx + 1
            day_offset = week * 7 + (slot_idx * 7 // max(total_ch, 1))
            sched = start + timedelta(days=day_offset)

            proof = proof_assets[len(briefs) % len(proof_assets)] if proof_assets else ""

            briefs.append({
                "brief_id": str(uuid.uuid4()),
                "pipeline_id": pipeline.get("pipeline_id", ""),
                "category": pipeline.get("category", ""),
                "channel": channel,
                "archetype": archetype,
                "persona": persona_name,
                "tone": persona.get("tone", ""),
                "hook": _hook_for(archetype, persona, blueprint),
                "angle": _angle_for(archetype, blueprint),
                "cta": pipeline.get("cta", ""),
                "proof_asset": proof,
                "voice_rules": pipeline.get("voice_rules", []),
                "do_not_say": pipeline.get("do_not_say", []),
                "scheduled_day": sched.isoformat(),
                "blueprint_version": pipeline.get("blueprint_version", ""),
                "approval_required": pipeline.get("approval_required", True),
                "status": store.STATUS_PENDING,
                "created_at": store.now_iso(),
            })

    briefs.sort(key=lambda b: b["scheduled_day"])
    return briefs


def _angle_for(archetype: str, blueprint: dict) -> str:
    for a in blueprint.get("content_archetypes", []):
        if a.get("name", "").lower() == archetype.lower():
            return a.get("summary", "")
    return ""


def _timeframe_weeks(timeframe: str) -> int:
    t = (timeframe or "week").lower().strip()
    if t in ("week", "weekly", "1w", "7d"):
        return 1
    m = re.match(r"(\d+)\s*w", t)
    if m:
        return max(1, int(m.group(1)))
    if t in ("month", "monthly", "4w"):
        return 4
    return 1


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


__all__ = ["generate_plan", "weekly_count"]
