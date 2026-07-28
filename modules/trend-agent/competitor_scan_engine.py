"""
EVA Trend Agent — Competitor Scan engine (deterministic month-over-month diff)
================================================================================

Diffs this month's directory snapshot against the most recent PRIOR month's
snapshot and classifies every new entrant as a real niche threat, a loose
adjacency, or noise.

No-Circularity Rule (same as trend_engine.py / app_scan_engine.py, tightened):
this engine makes NO network calls and NO LLM calls. A new entrant's threat
level is decided by a fixed keyword rule over the entry's own directory
description, so the verdict is reproducible from the snapshot files alone and
every call is spelled out in `flags`. The engine never invents a competitor,
never rewrites a description, and never upgrades a verdict on a hunch.

Why the rules are asymmetric: "acquisition" is overloaded. The niche EVA
actually competes in is BUY-SIDE deal sourcing + underwriting automation for
acquirers. Talent-acquisition/recruiting tools and generic lead-gen /
"customer acquisition" agents match the word but are not competitors, so they
are filtered as noise rather than allowed to fire a monthly alert.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from competitor_models import (
    CompetitorEntry,
    CompetitorScanRunInput,
    CompetitorScanRunResult,
)

COMPETITOR_SCAN_ENGINE_VERSION = "1.0.0"

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")
SNAPSHOT_GLOB = "competitor_scan_*.json"
_SNAPSHOT_MONTH_RE = re.compile(r"competitor_scan_(\d{4}-\d{2})\.json$")

# A new entrant is a real threat only if its own description names the buy-side
# deal-sourcing / underwriting work EVA does.
TIGHT_MATCH_TERMS = (
    "deal sourcing",
    "underwriting",
    "buy-side",
    "buy side",
    "m&a",
    "deal flow",
    "acquisition financing",
)

# Never a competitor no matter what else the listing says: "acquisition" here
# means hiring, not buying companies.
HARD_NOISE_TERMS = (
    "talent acquisition",
    "recruiting",
    "recruitment",
    "hiring",
    "ats",
    "applicant tracking",
)

# Competitor-shaped only if the listing ALSO names deal/M&A/underwriting work;
# on its own this is the generic lead-gen / sales-automation / CRM crowd (35+
# agents in the directory), which would otherwise drown the monthly signal.
SOFT_NOISE_TERMS = (
    "customer acquisition",
    "lead generation",
    "lead gen",
    "leadgen",
    "sales automation",
    "crm agent",
    "cold email",
    "prospecting",
)


def _contains_term(haystack: str, term: str) -> bool:
    """Whole-token match, so short tokens like "ats" don't fire inside
    "chats"/"stats" and multi-word phrases still match verbatim."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack, re.IGNORECASE) is not None


def is_tight_match(entry: CompetitorEntry) -> bool:
    """True when the entry's OWN description names EVA's niche work."""
    return any(_contains_term(entry.description, t) for t in TIGHT_MATCH_TERMS)


def is_noise(entry: CompetitorEntry) -> bool:
    """Noise = a false-positive keyword match, not a buy-side competitor."""
    hay = f"{entry.category} {entry.description}"
    if any(_contains_term(hay, t) for t in HARD_NOISE_TERMS):
        return True
    if any(_contains_term(hay, t) for t in SOFT_NOISE_TERMS) and not is_tight_match(entry):
        return True
    return False


def _snapshot_month(path: str) -> Optional[str]:
    match = _SNAPSHOT_MONTH_RE.search(os.path.basename(path))
    return match.group(1) if match else None


def find_previous_snapshot(scan_date: str, cases_dir: str = CASES_DIR) -> Optional[str]:
    """Path of the most recent snapshot strictly older than `scan_date`.

    `*_result.json` files are engine OUTPUT, not snapshots — the filename regex
    excludes them, so a previous run's result can never be diffed against.
    """
    months: list[tuple[str, str]] = []
    for path in glob.glob(os.path.join(cases_dir, SNAPSHOT_GLOB)):
        month = _snapshot_month(path)
        if month is not None and month < scan_date:
            months.append((month, path))
    if not months:
        return None
    return max(months)[1]


def _load_snapshot(path: str) -> CompetitorScanRunInput:
    with open(path, "r", encoding="utf-8") as fh:
        return CompetitorScanRunInput(**json.load(fh))


def _classify(entry: CompetitorEntry) -> tuple[str, str]:
    """(bucket, human-readable reason) for one new entrant."""
    if is_noise(entry):
        return "NOISE", "matched a noise category (talent-acquisition/recruiting or generic lead-gen) with no deal/M&A/underwriting term in its own description — excluded from threat assessment"
    if is_tight_match(entry):
        hits = [t for t in TIGHT_MATCH_TERMS if _contains_term(entry.description, t)]
        return "TIGHT", f"description names EVA's niche directly ({', '.join(hits)}) — direct buy-side competitor"
    return "LOOSE", "new entrant is only loosely adjacent (no buy-side deal-sourcing/underwriting term in its description) — monitor, do not treat as a direct competitor"


def run_competitor_scan(
    inp: CompetitorScanRunInput, cases_dir: str = CASES_DIR
) -> CompetitorScanRunResult:
    flags: list[str] = []
    previous_path = find_previous_snapshot(inp.scan_date, cases_dir)

    if previous_path is None:
        flags.append(
            f"baseline scan, nothing to diff against yet — {len(inp.entries)} entries recorded as the "
            f"{inp.scan_date} baseline; next month's run will diff against this file"
        )
        return CompetitorScanRunResult(
            scan_date=inp.scan_date,
            previous_scan_date=None,
            total_entries=len(inp.entries),
            new_entrants=[],
            verdict="NO_NEW_THREAT",
            flags=flags,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    previous = _load_snapshot(previous_path)
    previous_urls = {e.url for e in previous.entries}
    new_entrants = [e for e in inp.entries if e.url not in previous_urls]

    flags.append(
        f"diffed {len(inp.entries)} entries against {previous.scan_date} "
        f"({len(previous.entries)} entries) — {len(new_entrants)} new by url"
    )

    threats: list[CompetitorEntry] = []
    loose: list[CompetitorEntry] = []
    for entry in new_entrants:
        bucket, reason = _classify(entry)
        flags.append(f"NEW [{bucket}] {entry.name} ({entry.url}, matched '{entry.matched_keyword}'): {reason}")
        if bucket == "TIGHT":
            threats.append(entry)
        elif bucket == "LOOSE":
            loose.append(entry)

    if threats:
        verdict = "ALERT"
        flags.append(
            f"ALERT: {len(threats)} new direct buy-side competitor(s) entered the directory: "
            f"{', '.join(e.name for e in threats)}"
        )
    elif loose:
        verdict = "WATCH"
        flags.append(
            f"WATCH: {len(loose)} loosely-adjacent new entrant(s), no direct buy-side competitor: "
            f"{', '.join(e.name for e in loose)}"
        )
    else:
        verdict = "NO_NEW_THREAT"
        flags.append(
            "NO_NEW_THREAT: no new entrants in EVA's niche"
            + (" (all new listings classified as noise)" if new_entrants else "")
        )

    return CompetitorScanRunResult(
        scan_date=inp.scan_date,
        previous_scan_date=previous.scan_date,
        total_entries=len(inp.entries),
        new_entrants=new_entrants,
        verdict=verdict,
        flags=flags,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
