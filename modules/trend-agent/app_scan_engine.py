"""
EVA Trend Agent — App Category Scan engine (deterministic aggregation)
=========================================================================

Turns upstream-researched CategoryAppScan data (top 10 apps per category,
each with a sourced worth_second_look call) into a ranked, aggregated
report: per-category opportunity tier, a flattened cross-category
second-look list, and a priority-ordered pick list for short-term revenue
action.

No-Circularity Rule (same as trend_engine.py): this engine never decides
whether an app is "worth a second look" — that judgment comes from sourced
upstream research (see AppEntry.worth_second_look / second_look_reason).
The engine only counts, ranks, and tiers what research already supplied.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app_models import (
    AppScanRunInput,
    AppScanRunResult,
    CategoryAppScan,
    CategoryAppScanResult,
    SecondLookPick,
)

APP_SCAN_ENGINE_VERSION = "1.0.0"


def _opportunity_tier(ratio: float) -> str:
    """HIGH: half or more of the top 10 are second-look candidates — this
    category is ripe for immediate action. MEDIUM: some signal, worth
    monitoring. LOW: incumbents dominate, not a near-term target."""
    if ratio >= 0.5:
        return "HIGH"
    if ratio >= 0.2:
        return "MEDIUM"
    return "LOW"


def score_category(cat: CategoryAppScan) -> CategoryAppScanResult:
    second_look = [a for a in cat.top_apps if a.worth_second_look]
    ratio = round(len(second_look) / len(cat.top_apps), 2) if cat.top_apps else 0.0
    return CategoryAppScanResult(
        category=cat.category,
        vertical_alignment=cat.vertical_alignment,
        top_apps=cat.top_apps,
        second_look_apps=second_look,
        second_look_count=len(second_look),
        second_look_ratio=ratio,
        opportunity_tier=_opportunity_tier(ratio),
        research_synthesis=cat.research_synthesis,
    )


def run_app_scan(inp: AppScanRunInput) -> AppScanRunResult:
    scored_categories = [score_category(c) for c in inp.categories]

    total_apps = sum(len(c.top_apps) for c in scored_categories)
    total_second_look = sum(c.second_look_count for c in scored_categories)

    picks: list[SecondLookPick] = []
    for c in scored_categories:
        for a in c.second_look_apps:
            if a.priority_rank is not None:
                picks.append(
                    SecondLookPick(
                        category=c.category,
                        name=a.name,
                        platform_type=a.platform_type,
                        monetization=a.monetization,
                        reason=a.second_look_reason,
                        priority_rank=a.priority_rank,
                        sources=a.sources,
                    )
                )
    picks.sort(key=lambda p: p.priority_rank)

    flags: list[str] = []
    for c in scored_categories:
        if len(c.top_apps) != 10:
            flags.append(f"{c.category}: has {len(c.top_apps)} apps, not the expected 10 — re-check research completeness")
        if c.opportunity_tier == "HIGH":
            flags.append(f"{c.category}: HIGH opportunity tier ({c.second_look_count}/{len(c.top_apps)} second-look) — prioritize for immediate revenue action")
        if c.second_look_count == 0:
            flags.append(f"{c.category}: zero second-look candidates — category dominated by incumbents, deprioritize for short-term revenue")

    return AppScanRunResult(
        run_label=inp.run_label,
        run_date=inp.run_date,
        categories=scored_categories,
        total_apps_scanned=total_apps,
        total_second_look_apps=total_second_look,
        top_priority_picks=picks,
        flags=flags,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
