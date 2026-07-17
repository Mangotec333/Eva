"""
Offline test suite for the EVA Health Monitor (Architecture Directive rule #7).
No network: every test uses the ``StubHealthClient``. Runs with
``python -m pytest`` from this directory.

Each test builds a fresh service backed by a throwaway SQLite file, a small fixed
target list, and a stub probe client, so runs are isolated.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from database import STATUS_DOWN, STATUS_UP, Store
from http_client import ProbeResult, StubHealthClient
from service import HealthMonitorService

TARGETS = [
    {"name": "alpha", "url": "http://localhost:9001/health"},
    {"name": "beta", "url": "http://localhost:9002/health"},
]

UP = ProbeResult(ok=True, http_code=200, latency_ms=4.2)
DOWN = ProbeResult(ok=False, http_code=0, latency_ms=-1.0, error="refused")


def _fresh_service(threshold=3, responses=None, alert_sink=None):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-health-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    client = StubHealthClient(responses=responses, default=DOWN)
    svc = HealthMonitorService(
        store=Store(path),
        client=client,
        targets=[dict(t) for t in TARGETS],
        failure_threshold=threshold,
        alert_sink=alert_sink,
    )
    return svc, client


# ---------------------------------------------------------------------------
# healthy module recorded
# ---------------------------------------------------------------------------

def test_healthy_module_recorded():
    svc, _ = _fresh_service(responses={
        "http://localhost:9001/health": UP,
        "http://localhost:9002/health": UP,
    })
    result = svc.tick()
    assert result["monitored"] == 2
    assert result["up"] == 2
    assert result["down"] == 0
    status = {s["module"]: s for s in svc.status()}
    assert status["alpha"]["status"] == STATUS_UP
    assert status["alpha"]["latency_ms"] == 4.2
    assert status["alpha"]["http_code"] == 200


# ---------------------------------------------------------------------------
# down module recorded
# ---------------------------------------------------------------------------

def test_down_module_recorded():
    svc, _ = _fresh_service(responses={
        "http://localhost:9001/health": UP,
        # beta falls through to the stub's DOWN default
    })
    svc.tick()
    status = {s["module"]: s for s in svc.status()}
    assert status["alpha"]["status"] == STATUS_UP
    assert status["beta"]["status"] == STATUS_DOWN
    assert status["beta"]["consecutive_failures"] == 1
    # a raw check row exists for the down module
    checks = svc.recent_checks(module="beta")
    assert checks and checks[0]["status"] == STATUS_DOWN
    assert checks[0]["error"] == "refused"


# ---------------------------------------------------------------------------
# alert fires after N consecutive failures (and not before)
# ---------------------------------------------------------------------------

def test_alert_fires_after_n_consecutive_failures():
    svc, _ = _fresh_service(threshold=3)  # everything DOWN by default
    # tick 1 and 2: below threshold -> no alert yet
    r1 = svc.tick()
    assert r1["new_alerts"] == 0
    r2 = svc.tick()
    assert r2["new_alerts"] == 0
    assert svc.list_alerts(status="open") == []
    # tick 3: reaches threshold -> alert per down module
    r3 = svc.tick()
    assert r3["new_alerts"] == len(TARGETS)
    open_alerts = svc.list_alerts(status="open")
    assert {a["module"] for a in open_alerts} == {"alpha", "beta"}
    assert all(a["consecutive_failures"] >= 3 for a in open_alerts)


def test_alert_not_duplicated_while_open():
    svc, _ = _fresh_service(threshold=2)
    svc.tick()
    svc.tick()  # opens alerts
    assert len(svc.list_alerts(status="open")) == len(TARGETS)
    # a 4th/5th down tick must NOT open more alerts (idempotent alerting)
    svc.tick()
    svc.tick()
    assert len(svc.list_alerts()) == len(TARGETS)


def test_alert_resolves_on_recovery():
    svc, client = _fresh_service(threshold=2)
    svc.tick()
    svc.tick()  # both down -> alerts open
    assert len(svc.list_alerts(status="open")) == 2
    # alpha recovers
    client.set("http://localhost:9001/health", UP)
    result = svc.tick()
    assert result["resolved_alerts"] == 1
    open_now = {a["module"] for a in svc.list_alerts(status="open")}
    assert open_now == {"beta"}
    assert {a["module"] for a in svc.list_alerts(status="resolved")} == {"alpha"}


def test_alert_sink_invoked_on_alert():
    delivered = []
    svc, _ = _fresh_service(threshold=1, alert_sink=delivered.append)
    svc.tick()  # threshold 1 -> both fire immediately
    assert len(delivered) == len(TARGETS)
    assert all("DOWN" in a["message"] for a in delivered)


# ---------------------------------------------------------------------------
# ledger (append-only) + memory
# ---------------------------------------------------------------------------

def test_ledger_records_events():
    svc, _ = _fresh_service(threshold=1)
    svc.tick()
    events = {e["event_type"] for e in svc.query_ledger()}
    assert "checked" in events
    assert "alert_opened" in events


def test_ledger_is_append_only():
    svc, _ = _fresh_service()
    svc.tick()
    rows = svc.query_ledger()
    assert rows
    with svc.store._connect() as conn:
        with pytest.raises(Exception):
            conn.execute("UPDATE ledger SET actor='x' WHERE id=?", (rows[0]["id"],))
        with pytest.raises(Exception):
            conn.execute("DELETE FROM ledger WHERE id=?", (rows[0]["id"],))


def test_memory_roundtrip_and_last_run():
    svc, _ = _fresh_service()
    svc.set_memory("k", "v", source="test")
    assert svc.get_memory("k") == "v"
    svc.tick()
    assert svc.last_run()["last_tick"]


def test_tick_is_idempotent_and_cron_safe():
    svc, _ = _fresh_service(responses={
        "http://localhost:9001/health": UP,
        "http://localhost:9002/health": UP,
    })
    svc.tick()
    svc.tick()
    # two ticks -> two check rows per module, no alerts (all up)
    assert len(svc.recent_checks(module="alpha")) == 2
    assert svc.list_alerts() == []


def test_missing_mission_and_goals_is_graceful():
    svc, _ = _fresh_service()
    assert isinstance(svc.mission, str)
    assert isinstance(svc.current_goals, str)


# ---------------------------------------------------------------------------
# config loading
# ---------------------------------------------------------------------------

def test_default_targets_present():
    from config import default_targets
    targets = default_targets()
    names = {t["name"] for t in targets}
    assert {"deployer", "finance-tracker", "postcards"} <= names
    assert all(t["url"].endswith("/health") for t in targets)


def test_load_targets_falls_back_on_bad_config(tmp_path):
    from config import default_targets, load_targets
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert load_targets(str(bad)) == default_targets()


def test_load_targets_reads_valid_config(tmp_path):
    import json
    from config import load_targets
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps([{"name": "x", "url": "http://localhost:1/health"}]))
    targets = load_targets(str(cfg))
    assert targets == [{"name": "x", "url": "http://localhost:1/health"}]
