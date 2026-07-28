"""Unit tests for competitor_scan_engine.py — deterministic month-over-month
diff of the AI-agent-directory snapshots. No network, no LLM: every case writes
a fake previous-month snapshot into tmp_path and asserts the verdict."""

from __future__ import annotations

import json
import os

from competitor_models import CompetitorEntry, CompetitorScanRunInput
from competitor_scan_engine import find_previous_snapshot, is_noise, is_tight_match, run_competitor_scan


def _make_entry(name: str, description: str = "", category: str = "", slug: str | None = None) -> CompetitorEntry:
    return CompetitorEntry(
        name=name,
        url=f"https://agent.distributedapps.ai/agent/{slug or name.lower().replace(' ', '-')}",
        category=category,
        description=description,
        matched_keyword="deal sourcing",
        first_seen_scan="2026-08",
    )


def _write_snapshot(cases_dir, scan_date: str, entries: list[CompetitorEntry]) -> str:
    os.makedirs(cases_dir, exist_ok=True)
    path = os.path.join(str(cases_dir), f"competitor_scan_{scan_date}.json")
    snapshot = CompetitorScanRunInput(scan_date=scan_date, keywords=["deal sourcing"], entries=entries)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(snapshot.model_dump_json(indent=2))
    return path


def test_baseline_run_with_no_previous_snapshot(tmp_path):
    inp = CompetitorScanRunInput(
        scan_date="2026-07",
        keywords=["deal sourcing"],
        entries=[_make_entry("Ava", "Real-estate transaction copilot for listing agents.")],
    )
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "NO_NEW_THREAT"
    assert result.previous_scan_date is None
    assert result.new_entrants == []
    assert result.total_entries == 1
    assert any("baseline scan, nothing to diff against yet" in f for f in result.flags)


def test_no_new_entrants_is_no_new_threat(tmp_path):
    carried = _make_entry("Ava", "Real-estate transaction copilot for listing agents.")
    _write_snapshot(tmp_path, "2026-07", [carried])

    inp = CompetitorScanRunInput(scan_date="2026-08", keywords=["deal sourcing"], entries=[carried])
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "NO_NEW_THREAT"
    assert result.previous_scan_date == "2026-07"
    assert result.new_entrants == []


def test_new_entrant_that_is_noise_does_not_alert(tmp_path):
    _write_snapshot(tmp_path, "2026-07", [_make_entry("Ava", "Real-estate transaction copilot.")])

    recruiter = _make_entry(
        "HireFlow",
        "Talent acquisition agent that screens candidates and manages the hiring pipeline.",
        category="Recruiting",
    )
    leadgen = _make_entry(
        "PipelineBot",
        "Lead generation agent that finds prospects and automates customer acquisition outreach.",
        category="Sales",
    )
    inp = CompetitorScanRunInput(
        scan_date="2026-08",
        keywords=["deal sourcing"],
        entries=[_make_entry("Ava", "Real-estate transaction copilot."), recruiter, leadgen],
    )
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "NO_NEW_THREAT"
    assert len(result.new_entrants) == 2
    assert any("all new listings classified as noise" in f for f in result.flags)
    assert any("NEW [NOISE] HireFlow" in f for f in result.flags)
    assert any("NEW [NOISE] PipelineBot" in f for f in result.flags)


def test_new_entrant_with_tight_match_alerts(tmp_path):
    _write_snapshot(tmp_path, "2026-07", [_make_entry("Ava", "Real-estate transaction copilot.")])

    competitor = _make_entry(
        "AcquireIQ",
        "Buy-side deal sourcing and underwriting automation for private equity acquirers and search funds.",
        category="Finance",
    )
    inp = CompetitorScanRunInput(
        scan_date="2026-08",
        keywords=["deal sourcing"],
        entries=[_make_entry("Ava", "Real-estate transaction copilot."), competitor],
    )
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "ALERT"
    assert [e.name for e in result.new_entrants] == ["AcquireIQ"]
    assert any("NEW [TIGHT] AcquireIQ" in f for f in result.flags)
    assert any("new direct buy-side competitor" in f for f in result.flags)


def test_new_entrant_with_loose_match_watches(tmp_path):
    _write_snapshot(tmp_path, "2026-07", [_make_entry("Ava", "Real-estate transaction copilot.")])

    adjacent = _make_entry(
        "Leni",
        "Analytics and reporting dashboards over residential rent roll and occupancy data for property owners.",
        category="Real Estate Analytics",
    )
    inp = CompetitorScanRunInput(
        scan_date="2026-08",
        keywords=["deal sourcing"],
        entries=[_make_entry("Ava", "Real-estate transaction copilot."), adjacent],
    )
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "WATCH"
    assert [e.name for e in result.new_entrants] == ["Leni"]
    assert any("NEW [LOOSE] Leni" in f for f in result.flags)


def test_lead_gen_agent_that_also_does_deal_sourcing_is_not_noise():
    """Soft noise is only noise when the listing has no niche term of its own —
    otherwise a real competitor could hide behind the word "prospecting"."""
    entry = _make_entry(
        "DealProspector",
        "Prospecting agent for buy-side deal sourcing: finds acquisition targets and drafts underwriting memos.",
        category="Sales",
    )
    assert is_tight_match(entry)
    assert not is_noise(entry)


def test_hard_noise_wins_even_with_a_niche_term():
    """Recruiting tools are never competitors, even when a listing name-drops M&A."""
    entry = _make_entry(
        "TalentM&A",
        "Talent acquisition platform for recruiting teams at firms going through an M&A integration.",
        category="Recruiting",
    )
    assert is_noise(entry)


def test_word_boundary_prevents_ats_substring_false_positive():
    entry = _make_entry("ChatStats", "Analyzes chats and stats for customer support teams.")
    assert not is_noise(entry)


def test_result_files_are_never_diffed_against(tmp_path):
    """`*_result.json` is engine output; treating it as a snapshot would diff a
    result against a snapshot and corrupt the month-over-month chain."""
    _write_snapshot(tmp_path, "2026-07", [_make_entry("Ava", "copilot")])
    with open(os.path.join(str(tmp_path), "competitor_scan_2026-08_result.json"), "w", encoding="utf-8") as fh:
        json.dump({"scan_date": "2026-08", "verdict": "NO_NEW_THREAT"}, fh)

    assert find_previous_snapshot("2026-09", cases_dir=str(tmp_path)).endswith("competitor_scan_2026-07.json")


def test_seeded_july_baseline_classifies_as_loose_adjacencies():
    """The hand-seeded 2026-07 baseline must not contain anything that would
    fire a false ALERT when August diffs against it."""
    from competitor_scan_engine import CASES_DIR

    with open(os.path.join(CASES_DIR, "competitor_scan_2026-07.json"), "r", encoding="utf-8") as fh:
        baseline = CompetitorScanRunInput(**json.load(fh))

    assert len(baseline.entries) == 6
    for entry in baseline.entries:
        assert not is_tight_match(entry), f"{entry.name} would fire a false ALERT"
        assert not is_noise(entry), f"{entry.name} would be silently dropped as noise"
