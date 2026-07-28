"""
EVA Trend Agent — Competitor Scan models
==========================================

Third capability of the trend-agent module (alongside the macro sector
durability stress-test in models.py / trend_engine.py and the app category
scan in app_models.py / app_scan_engine.py). This mode watches a public
AI-agent directory (https://agent.distributedapps.ai/directory, 4,515+ agents,
AIVSS-scored) for NEW agents entering EVA's actual niche — buy-side deal
sourcing and underwriting automation for acquirers (PE / ETA / family
offices) — and diffs each month's snapshot against the previous month's.

Unlike Mode 1 and Mode 2, the raw input here is NOT upstream LLM research: it
is a plain HTTP fetch of the directory (competitor_fetch.py), so a run costs
~$0 in ongoing LLM/API credits. The No-Circularity Rule still holds, in a
stronger form — the engine (competitor_scan_engine.py) never asks a model
whether a new entrant is a threat. Threat classification is a deterministic
keyword rule over the entry's OWN description, so the same snapshot always
yields the same verdict and every call is explained in `flags`.

Niche note (why the keyword rules are tight): "acquisition" is a heavily
overloaded term. Talent-acquisition/recruiting tools and generic
lead-gen/"customer acquisition" agents match it as false positives and are
filtered as noise — see NOISE_TERMS in competitor_scan_engine.py.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CompetitorEntry(BaseModel):
    """One agent listing pulled from the directory. Every field is read
    straight off the directory page — nothing is inferred or invented."""

    name: str
    url: str = Field(..., description="Canonical directory URL for this agent — the dedupe + diff key")
    category: str = Field("", description="Directory-assigned category, verbatim")
    description: str = Field("", description="Directory-supplied description, verbatim. Threat classification reads THIS field only.")
    aivss_score: Optional[float] = Field(
        None, description="AIVSS security score as published by the directory; None when the listing shows none"
    )
    matched_keyword: str = Field("", description="Which search term surfaced this entry (provenance for why it is in the snapshot)")
    first_seen_scan: str = Field("", description="scan_date (YYYY-MM) of the snapshot this entry first appeared in")


class CompetitorScanRunInput(BaseModel):
    """One month's directory snapshot, as written by competitor_fetch.py."""

    scan_date: str = Field(..., description="YYYY-MM of this snapshot")
    keywords: list[str] = Field(default_factory=list, description="Search terms queried to build this snapshot")
    entries: list[CompetitorEntry] = Field(default_factory=list, description="Deduped, noise-filtered listings")
    source_notes: str = Field("", description="Provenance for this snapshot — e.g. which terms returned zero results, or that it was hand-seeded from a manual sweep")


class CompetitorScanRunResult(BaseModel):
    scan_date: str
    previous_scan_date: Optional[str] = Field(
        None, description="scan_date of the prior-month snapshot diffed against; None on a baseline (first) run"
    )
    total_entries: int
    new_entrants: list[CompetitorEntry] = Field(
        default_factory=list, description="Entries present this scan and absent from the previous one, by url"
    )
    verdict: Literal["NO_NEW_THREAT", "WATCH", "ALERT"] = Field(
        ..., description="ALERT: a new entrant is a tight, non-noise niche match. WATCH: new entrants are only loosely relevant. NO_NEW_THREAT: none, or noise only."
    )
    flags: list[str] = Field(
        default_factory=list, description="Human-readable line per new entrant plus the verdict rationale"
    )
    computed_at: str = ""
