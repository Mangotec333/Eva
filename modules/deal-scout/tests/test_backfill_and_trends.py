"""Tests for the backfill importer and the trend analyzer."""

import os

from backfill import backfill_all, backfill_closed, backfill_open
from pipeline import score_pending
from trends import analyze_trends, build_and_save_report, render_markdown


def test_backfill_imports_open_and_closed(store, fixtures_dir):
    res = backfill_all(
        store,
        data_dir=os.path.join(fixtures_dir, "deal_scout_data"),
        closed_path=os.path.join(fixtures_dir, "closed_deals_dataset.json"),
    )
    assert res["open"]["imported_files"] == 1
    assert res["closed"]["imported"] == 4
    assert len(store.list_raw_deals(is_closed=False)) == 4
    assert len(store.list_raw_deals(is_closed=True)) == 4


def test_backfill_missing_files_skip_gracefully(store):
    res = backfill_open(store, data_dir="/nonexistent/dir")
    assert res["imported_files"] == 0 and "skipped" in res["note"]
    res2 = backfill_closed(store, path="/nonexistent/file.json")
    assert res2["imported"] == 0 and "skipped" in res2["note"]


def test_gate_after_backfill(store, fixtures_dir):
    backfill_all(
        store,
        data_dir=os.path.join(fixtures_dir, "deal_scout_data"),
        closed_path=os.path.join(fixtures_dir, "closed_deals_dataset.json"),
    )
    result = score_pending(store)
    # EF(GB, high trust) + Flippa(US) + Acquire(US) scored; Flippa(FR) skipped.
    assert result["scored"] == 3
    assert result["skipped"] == 1


def test_trends_stats_and_report(store, fixtures_dir):
    backfill_all(
        store,
        data_dir=os.path.join(fixtures_dir, "deal_scout_data"),
        closed_path=os.path.join(fixtures_dir, "closed_deals_dataset.json"),
    )
    stats = analyze_trends(store)
    assert stats["totals"] == {"all": 8, "open": 4, "sold": 4}
    assert stats["median_multiple"]["sold"] > 0
    assert stats["profile_sold"]["count"] == 4
    assert stats["sale_drivers"]                       # non-empty inferred drivers
    md = render_markdown(stats)
    assert "Median Annual Multiple" in md
    assert "Inferred Sale Drivers" in md


def test_build_and_save_report_writes_file(store, fixtures_dir, tmp_path):
    backfill_all(
        store,
        data_dir=os.path.join(fixtures_dir, "deal_scout_data"),
        closed_path=os.path.join(fixtures_dir, "closed_deals_dataset.json"),
    )
    out = tmp_path / "report.md"
    report = build_and_save_report(store, output_path=str(out))
    assert out.exists()
    assert report.report_md.startswith("#")
    assert store.latest_trend_report().id == report.id
