"""Tests for the FastAPI app's scheduler wiring and /pipeline/run-now endpoint.

Requires ``fastapi``, ``aiosqlite`` and ``apscheduler`` to actually import
``main`` (it pulls in the full app, including the legacy aiosqlite-backed
``database`` module). This dev sandbox has no internet access to install
those, so this whole module is skipped here via ``pytest.importorskip`` and is
expected to run for real on the live deploy host, where requirements.txt is
installed.

Covers:
  * the scheduler job is registered on startup (TestClient + lifespan context,
    ``scheduler.get_jobs()`` has the expected job id);
  * ``POST /pipeline/run-now`` calls ``run_pipeline_cycle`` and returns its
    summary dict, with ``run_pipeline_cycle`` itself monkeypatched so the
    endpoint test never touches the real EF network path.
  * ``run_pipeline_cycle`` is exercised separately (with fully fake
    dependencies, no mocked endpoint) in ``test_scheduler.py``.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in this environment")
pytest.importorskip("aiosqlite", reason="aiosqlite not installed in this environment")
pytest.importorskip("apscheduler", reason="apscheduler not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from scheduler import PIPELINE_CYCLE_JOB_ID  # noqa: E402


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Point both the legacy aiosqlite DB and the pipeline SQLite DB at tmp files."""
    import database as db

    legacy_path = str(tmp_path / "legacy.db")
    pipeline_path = str(tmp_path / "pipeline.db")
    monkeypatch.setattr(db, "DB_PATH", legacy_path)
    monkeypatch.setattr(main, "PIPELINE_DB_PATH", pipeline_path)
    yield


def test_scheduler_job_registered_on_startup(isolated_db, monkeypatch):
    monkeypatch.delenv("DEAL_SCOUT_DISABLE_SCHEDULER", raising=False)
    monkeypatch.setenv("DEAL_SCOUT_CYCLE_HOURS", "6")

    with TestClient(main.app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200

        scheduler = client.app.state.scheduler
        assert scheduler is not None
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == PIPELINE_CYCLE_JOB_ID
    # Scheduler is shut down cleanly on lifespan exit — no assertion needed
    # beyond the context manager not raising.


def test_scheduler_can_be_disabled_via_env(isolated_db, monkeypatch):
    monkeypatch.setenv("DEAL_SCOUT_DISABLE_SCHEDULER", "1")
    try:
        with TestClient(main.app) as client:
            assert client.app.state.scheduler is None
    finally:
        monkeypatch.delenv("DEAL_SCOUT_DISABLE_SCHEDULER", raising=False)


def test_run_now_endpoint_calls_run_pipeline_cycle(isolated_db, monkeypatch):
    monkeypatch.setenv("DEAL_SCOUT_DISABLE_SCHEDULER", "1")  # keep this test focused on the endpoint

    captured = {}

    def fake_run_pipeline_cycle(store, *args, **kwargs):
        captured["called"] = True
        captured["store"] = store
        return {
            "sourced": 3, "scored": 2, "box_evaluated": 2, "box_passed": 1,
            "errors": [], "discover": {}, "score": {}, "box_type": "real_estate",
        }

    monkeypatch.setattr(main, "run_pipeline_cycle", fake_run_pipeline_cycle)

    with TestClient(main.app) as client:
        resp = client.post("/pipeline/run-now")

    assert resp.status_code == 200
    body = resp.json()
    assert captured.get("called") is True
    assert body == {
        "sourced": 3, "scored": 2, "box_evaluated": 2, "box_passed": 1,
        "errors": [], "discover": {}, "score": {}, "box_type": "real_estate",
    }
