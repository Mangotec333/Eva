"""Baseline offline tests for the EVA launcher (health + status helpers, no network)."""

import eva_launcher
from fastapi.testclient import TestClient


def test_health_endpoint_returns_online():
    client = TestClient(eva_launcher.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert body["service"] == "eva_launcher"


def test_port_is_listening_false_on_unused_port():
    # Port 1 is privileged and not listening in the sandbox.
    assert eva_launcher.port_is_listening(1) is False


def test_service_status_returns_known_string():
    status = eva_launcher.service_status("screenpipe")
    assert status in ("online", "offline", "unknown")


def test_all_statuses_covers_every_service():
    statuses = eva_launcher.all_statuses()
    assert set(statuses.keys()) == set(eva_launcher.SERVICES.keys())
    assert all(v in ("online", "offline", "unknown") for v in statuses.values())
