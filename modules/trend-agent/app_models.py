"""
EVA Trend Agent — App Category Scan models
=============================================

Second capability of the trend-agent module (alongside the macro sector
durability stress-test in models.py / trend_engine.py). This mode tracks the
TOP 10 apps/products in each venture-aligned category every run (mobile apps,
SaaS/web products, and acquirable marketplace listings), captures the need
each one serves and its gap, and flags which ones are "worth a second look"
for SHORT-TERM revenue (weeks-to-months: clone, acquire, or white-label) —
as opposed to the long-horizon durability thesis the sector engine tests.

Same philosophy as the sector engine: the qualitative research (what the top
10 are, their gaps, their monetization, whether they're worth a second look)
is done upstream by Perplexity / an EVA research subagent and supplied as
case JSON with sources (see cases/app_scan_2026-07.json). This module's
engine (app_scan_engine.py) only aggregates and ranks that research — it
never invents an app, a gap, or a "worth a second look" call on its own.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AppEntry(BaseModel):
    """One app/product in a category's top 10. Every field is sourced from
    upstream research (see `sources`) — not guessed."""

    rank: int = Field(..., ge=1, le=10, description="Position in this category's top 10, as researched")
    name: str
    platform_type: str = Field(
        ..., description="mobile_app | saas_web | marketplace_listing | consumer_app"
    )
    description: str = Field(..., description="One-line description of what it does")
    core_need: str = Field(..., description="The underlying user/buyer problem it serves")
    gap_weakness: str = Field(..., description="Notable gap, weakness, or unmet sub-need in its current offering")
    monetization: str = Field(..., description="Pricing/monetization model, or asking price + multiple if a marketplace listing")
    worth_second_look: bool = Field(
        ..., description="Upstream research judgment: is this a candidate to clone/acquire/white-label for short-term (weeks-to-months) revenue?"
    )
    second_look_reason: str = Field("", description="One-sentence reason for the worth_second_look call")
    priority_rank: Optional[int] = Field(
        None, description="Optional cross-category priority (1 = strongest) assigned by upstream research to second-look candidates only"
    )
    sources: list[str] = Field(default_factory=list, description="URLs the entry is grounded in")


class CategoryAppScan(BaseModel):
    """Raw research input for one category: its top 10 apps."""

    category: str
    vertical_alignment: str = Field(
        ..., description="Which of the user's ventures this category maps to (EVA / Storeys RCFE / Storeys Healthcare CRE / Storeys RE Fund / AI Growth Agency / Digital Acquisition)"
    )
    top_apps: list[AppEntry]
    research_synthesis: str = Field("", description="Upstream research's narrative synthesis of unmet needs across this category's top 10")


class AppScanRunInput(BaseModel):
    run_label: str
    run_date: str
    categories: list[CategoryAppScan]
    source_notes: str = ""


class CategoryAppScanResult(BaseModel):
    category: str
    vertical_alignment: str
    top_apps: list[AppEntry]
    second_look_apps: list[AppEntry]
    second_look_count: int
    second_look_ratio: float = Field(..., description="second_look_count / len(top_apps), COMPUTED")
    opportunity_tier: str = Field(..., description="HIGH | MEDIUM | LOW, COMPUTED from second_look_ratio")
    research_synthesis: str


class SecondLookPick(BaseModel):
    category: str
    name: str
    platform_type: str
    monetization: str
    reason: str
    priority_rank: Optional[int]
    sources: list[str]


class AppScanRunResult(BaseModel):
    run_label: str
    run_date: str
    categories: list[CategoryAppScanResult]
    total_apps_scanned: int
    total_second_look_apps: int
    top_priority_picks: list[SecondLookPick] = Field(
        default_factory=list, description="Second-look apps with a priority_rank, sorted ascending (1 = strongest), COMPUTED"
    )
    flags: list[str] = Field(default_factory=list)
    computed_at: str = ""


class AppScanAgentHealth(BaseModel):
    status: str
    module: str
    version: str
    directive_version: str
