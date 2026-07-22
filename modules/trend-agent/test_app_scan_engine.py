"""Unit tests for app_scan_engine.py — deterministic aggregation of researched
top-10-per-category app data into an opportunity-tiered report."""

from __future__ import annotations

from app_models import AppEntry, AppScanRunInput, CategoryAppScan
from app_scan_engine import run_app_scan, score_category, _opportunity_tier


def _make_app(rank: int, worth: bool, priority: int | None = None) -> AppEntry:
    return AppEntry(
        rank=rank,
        name=f"App{rank}",
        platform_type="saas_web",
        description="d",
        core_need="n",
        gap_weakness="g",
        monetization="$10/mo",
        worth_second_look=worth,
        second_look_reason="r" if worth else "",
        priority_rank=priority,
        sources=["https://example.com"],
    )


def test_opportunity_tier_thresholds():
    assert _opportunity_tier(0.6) == "HIGH"
    assert _opportunity_tier(0.5) == "HIGH"
    assert _opportunity_tier(0.3) == "MEDIUM"
    assert _opportunity_tier(0.2) == "MEDIUM"
    assert _opportunity_tier(0.1) == "LOW"
    assert _opportunity_tier(0.0) == "LOW"


def test_score_category_counts_second_look_and_tiers():
    cat = CategoryAppScan(
        category="Test Category",
        vertical_alignment="EVA",
        top_apps=[_make_app(i, worth=(i <= 6)) for i in range(1, 11)],
        research_synthesis="synthesis",
    )
    scored = score_category(cat)
    assert scored.second_look_count == 6
    assert scored.second_look_ratio == 0.6
    assert scored.opportunity_tier == "HIGH"
    assert len(scored.second_look_apps) == 6


def test_run_app_scan_end_to_end_ranks_priority_picks():
    cat_high = CategoryAppScan(
        category="High Opportunity",
        vertical_alignment="EVA",
        top_apps=[
            _make_app(1, worth=True, priority=2),
            _make_app(2, worth=True, priority=1),
            _make_app(3, worth=True),
            _make_app(4, worth=True),
            _make_app(5, worth=True),
            *[_make_app(i, worth=False) for i in range(6, 11)],
        ],
        research_synthesis="s1",
    )
    cat_low = CategoryAppScan(
        category="Low Opportunity",
        vertical_alignment="Storeys",
        top_apps=[_make_app(i, worth=False) for i in range(1, 11)],
        research_synthesis="s2",
    )
    inp = AppScanRunInput(run_label="test-run", run_date="2026-07", categories=[cat_high, cat_low])
    result = run_app_scan(inp)

    assert result.total_apps_scanned == 20
    assert result.total_second_look_apps == 5
    # priority_rank=1 (App2) should sort ahead of priority_rank=2 (App1); apps
    # without a priority_rank are excluded from the ranked pick list.
    assert [p.name for p in result.top_priority_picks] == ["App2", "App1"]
    assert any("HIGH opportunity tier" in f for f in result.flags)
    assert any("zero second-look candidates" in f for f in result.flags)


def test_run_app_scan_flags_incomplete_top_ten():
    cat = CategoryAppScan(
        category="Incomplete",
        vertical_alignment="EVA",
        top_apps=[_make_app(i, worth=False) for i in range(1, 6)],
        research_synthesis="s",
    )
    result = run_app_scan(AppScanRunInput(run_label="r", run_date="2026-07", categories=[cat]))
    assert any("not the expected 10" in f for f in result.flags)
