"""Tests for the competitor_data_store STUB.

Two things matter here: (1) the tables can be created and rows round-tripped,
and (2) the store is genuinely inert by default, so merging this cannot change
the behaviour of the scheduled monthly scan. Offline — sqlite only, no network.
"""

from __future__ import annotations

import importlib
import os

import competitor_data_store


def _store_at(tmp_path, enabled: bool, project: str | None = None):
    """Reload the module with env pointed at a throwaway DB, since DB_PATH and the
    flag are read at import time."""
    os.environ["EVA_COMPETITOR_DB_PATH"] = str(tmp_path / "competitor_data.db")
    os.environ["EVA_COMPETITOR_DB_STORE_ENABLED"] = "true" if enabled else "false"
    if project is None:
        os.environ.pop("EVA_PROJECT_ID", None)
    else:
        os.environ["EVA_PROJECT_ID"] = project
    return importlib.reload(competitor_data_store)


def teardown_function():
    for key in ("EVA_COMPETITOR_DB_PATH", "EVA_COMPETITOR_DB_STORE_ENABLED", "EVA_PROJECT_ID"):
        os.environ.pop(key, None)
    importlib.reload(competitor_data_store)


def test_disabled_by_default_writes_nothing(tmp_path):
    os.environ["EVA_COMPETITOR_DB_PATH"] = str(tmp_path / "competitor_data.db")
    os.environ.pop("EVA_COMPETITOR_DB_STORE_ENABLED", None)
    store = importlib.reload(competitor_data_store)

    assert store.is_enabled() is False
    assert store.record_scan_run(None, "deal sourcing", [{"name": "X"}], 1) is None
    assert store.record_verdict(None, "ALERT", {"flags": []}) is None
    # Not even the DB file is created when the flag is off.
    assert not os.path.exists(store.DB_PATH)


def test_enabled_store_round_trips_a_scan_run(tmp_path):
    store = _store_at(tmp_path, enabled=True)

    raw = [{"name": "Ava", "url": "https://agent.distributedapps.ai/directory/ava", "aivss_score": 8.7}]
    row_id = store.record_scan_run(None, "deal sourcing", raw, len(raw))
    assert row_id

    runs = store.list_scan_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == row_id
    assert runs[0]["term"] == "deal sourcing"
    assert runs[0]["agent_count"] == 1
    assert runs[0]["raw_results"] == raw
    assert runs[0]["project_id"] == "default"
    assert runs[0]["run_at"]


def test_enabled_store_round_trips_a_verdict(tmp_path):
    store = _store_at(tmp_path, enabled=True)

    details = {"scan_date": "2026-08", "new_entrants": ["AcquireIQ"], "flags": ["NEW [TIGHT] AcquireIQ"]}
    row_id = store.record_verdict(None, "ALERT", details)
    assert row_id

    verdicts = store.list_verdicts()
    assert len(verdicts) == 1
    assert verdicts[0]["verdict"] == "ALERT"
    assert verdicts[0]["details"] == details


def test_rows_are_scoped_by_project(tmp_path):
    store = _store_at(tmp_path, enabled=True)

    store.record_scan_run("project-a", "M&A", [], 0)
    store.record_scan_run("project-b", "M&A", [], 0)

    assert len(store.list_scan_runs()) == 2
    assert [r["project_id"] for r in store.list_scan_runs("project-a")] == ["project-a"]
    assert len(store.list_scan_runs("project-b")) == 1


def test_project_id_falls_back_to_the_env_var(tmp_path):
    store = _store_at(tmp_path, enabled=True, project="eva-main")
    store.record_verdict(None, "NO_NEW_THREAT", {})
    assert store.list_verdicts()[0]["project_id"] == "eva-main"


def test_full_raw_payload_is_kept_not_just_the_diff(tmp_path):
    """The point of the corpus: entries the snapshot filters out as noise are
    still recorded, so a later mining pass can revisit the filter decisions."""
    store = _store_at(tmp_path, enabled=True)

    raw = [
        {"name": "Gene", "category": "Lead Generation", "description": "AI sales agent"},
        {"name": "Ava", "category": "Personal Assistant", "description": "real estate transactions"},
    ]
    store.record_scan_run(None, "real estate", raw, len(raw))

    stored = store.list_scan_runs()[0]["raw_results"]
    assert [e["name"] for e in stored] == ["Gene", "Ava"]


def test_scan_flow_is_unchanged_when_the_store_is_disabled(tmp_path):
    """A full engine run must produce the same verdict with the flag off, and
    leave no DB file behind."""
    os.environ["EVA_COMPETITOR_DB_PATH"] = str(tmp_path / "competitor_data.db")
    os.environ.pop("EVA_COMPETITOR_DB_STORE_ENABLED", None)
    store = importlib.reload(competitor_data_store)

    from competitor_models import CompetitorEntry, CompetitorScanRunInput
    from competitor_scan_engine import run_competitor_scan

    inp = CompetitorScanRunInput(
        scan_date="2026-07",
        keywords=["deal sourcing"],
        entries=[
            CompetitorEntry(
                name="Ava",
                url="https://agent.distributedapps.ai/directory/ava",
                description="Your intelligent AI assistant for real estate transactions.",
            )
        ],
    )
    result = run_competitor_scan(inp, cases_dir=str(tmp_path))

    assert result.verdict == "NO_NEW_THREAT"
    assert not os.path.exists(store.DB_PATH)
