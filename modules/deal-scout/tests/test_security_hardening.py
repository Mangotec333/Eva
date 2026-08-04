"""Tests for security hardening added after the pre-publish security review.

Covers:
  * DEAL_SCOUT_API_KEY middleware guards mutation endpoints (POST/PUT/DELETE)
    when set, is a no-op when unset, and always exempts /pipeline/run-now
    (which has its own independent RUN_NOW_TOKEN check).
  * /pipeline/trends/report rejects an `output` query param that would
    resolve outside the server-controlled reports directory (path
    traversal / arbitrary file write).

Requires ``fastapi``, ``aiosqlite`` and ``apscheduler`` to import ``main``.
This dev sandbox has no internet access to install those, so this whole
module is skipped here via ``pytest.importorskip`` and is expected to run
for real on the live deploy host, where requirements.txt is installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in this environment")
pytest.importorskip("aiosqlite", reason="aiosqlite not installed in this environment")
pytest.importorskip("apscheduler", reason="apscheduler not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    import database as db

    legacy_path = str(tmp_path / "legacy.db")
    pipeline_path = str(tmp_path / "pipeline.db")
    monkeypatch.setattr(db, "DB_PATH", legacy_path)
    monkeypatch.setattr(main, "PIPELINE_DB_PATH", pipeline_path)
    monkeypatch.setenv("DEAL_SCOUT_DISABLE_SCHEDULER", "1")
    yield


def test_mutation_blocked_without_api_key_when_configured(isolated_db, monkeypatch):
    monkeypatch.setenv("DEAL_SCOUT_API_KEY", "topsecret")
    try:
        with TestClient(main.app) as client:
            resp = client.post("/pipeline/score")
            assert resp.status_code == 403
            resp = client.post("/pipeline/score", headers={"x-api-key": "wrong"})
            assert resp.status_code == 403
    finally:
        monkeypatch.delenv("DEAL_SCOUT_API_KEY", raising=False)


def test_mutation_allowed_with_correct_api_key(isolated_db, monkeypatch):
    monkeypatch.setenv("DEAL_SCOUT_API_KEY", "topsecret")
    monkeypatch.setattr(main, "score_pending", lambda store: {"scored": 0, "skipped": 0})
    try:
        with TestClient(main.app) as client:
            resp = client.post("/pipeline/score", headers={"x-api-key": "topsecret"})
            assert resp.status_code == 200
    finally:
        monkeypatch.delenv("DEAL_SCOUT_API_KEY", raising=False)


def test_mutation_open_when_api_key_unset(isolated_db, monkeypatch):
    monkeypatch.delenv("DEAL_SCOUT_API_KEY", raising=False)
    monkeypatch.setattr(main, "score_pending", lambda store: {"scored": 0, "skipped": 0})
    with TestClient(main.app) as client:
        resp = client.post("/pipeline/score")
        assert resp.status_code == 200


def test_run_now_exempt_from_api_key_guard(isolated_db, monkeypatch):
    """/pipeline/run-now has its own RUN_NOW_TOKEN check and must stay reachable
    even when DEAL_SCOUT_API_KEY is set, without needing the x-api-key header."""
    monkeypatch.setenv("DEAL_SCOUT_API_KEY", "topsecret")
    monkeypatch.delenv("RUN_NOW_TOKEN", raising=False)
    monkeypatch.setattr(main, "run_pipeline_cycle", lambda store, *a, **k: {"ok": True})
    try:
        with TestClient(main.app) as client:
            resp = client.post("/pipeline/run-now")
            assert resp.status_code == 200
    finally:
        monkeypatch.delenv("DEAL_SCOUT_API_KEY", raising=False)


def test_get_endpoints_never_blocked_by_api_key_guard(isolated_db, monkeypatch):
    monkeypatch.setenv("DEAL_SCOUT_API_KEY", "topsecret")
    try:
        with TestClient(main.app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
    finally:
        monkeypatch.delenv("DEAL_SCOUT_API_KEY", raising=False)


def test_trends_report_rejects_path_traversal(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setenv("DEAL_SCOUT_REPORTS_DIR", str(tmp_path / "reports"))
    try:
        with TestClient(main.app) as client:
            resp = client.post(
                "/pipeline/trends/report",
                params={"output": "../../etc/evil.md"},
            )
            assert resp.status_code == 400
    finally:
        monkeypatch.delenv("DEAL_SCOUT_REPORTS_DIR", raising=False)


def test_trends_report_rejects_absolute_path_outside_reports_dir(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setenv("DEAL_SCOUT_REPORTS_DIR", str(tmp_path / "reports"))
    try:
        with TestClient(main.app) as client:
            resp = client.post(
                "/pipeline/trends/report",
                params={"output": "/tmp/somewhere-else/evil.md"},
            )
            assert resp.status_code == 400
    finally:
        monkeypatch.delenv("DEAL_SCOUT_REPORTS_DIR", raising=False)


def test_trends_report_allows_bare_filename_inside_reports_dir(isolated_db, monkeypatch, tmp_path):
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("DEAL_SCOUT_REPORTS_DIR", str(reports_dir))
    try:
        with TestClient(main.app) as client:
            resp = client.post(
                "/pipeline/trends/report",
                params={"output": "legit_report.md"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["output_path"].startswith(str(reports_dir))
            assert (reports_dir / "legit_report.md").exists()
    finally:
        monkeypatch.delenv("DEAL_SCOUT_REPORTS_DIR", raising=False)
