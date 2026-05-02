from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.bridge.app import create_app
from services.brain.schema import TaskStatus
from services.model.provider import HeuristicModelProvider
from services.protocols.contracts import PROTOCOL_VERSION


@pytest.fixture()
def client() -> TestClient:
    app = create_app(model_provider=HeuristicModelProvider())
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["status"] == "ok"
    assert payload["model_provider"] == "HeuristicModelProvider"
    assert "started_at" in payload


def test_protocols_endpoint(client: TestClient) -> None:
    response = client.get("/protocols")
    assert response.status_code == 200
    payload = response.json()
    names = {p["name"] for p in payload["protocols"]}
    assert {"task.http", "health.http", "capabilities.http", "events.sse"} <= names
    assert payload["protocol_version"] == PROTOCOL_VERSION


def test_capabilities_endpoint(client: TestClient) -> None:
    response = client.get("/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_provider"] == "HeuristicModelProvider"
    names = {c["name"] for c in payload["capabilities"]}
    assert "answer.text" in names
    assert "approval.required" in names
    approval = next(c for c in payload["capabilities"] if c["name"] == "approval.required")
    assert approval["requires_approval"] is True


def test_task_endpoint_safe_request(client: TestClient) -> None:
    response = client.post(
        "/task",
        json={
            "channel": "bridge_http",
            "request": {"utterance": "hello eva"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["requires_approval"] is False
    assert payload["response"]["status"] == TaskStatus.COMPLETED.value
    assert "EVA Phase 1" in payload["response"]["text"]


def test_task_endpoint_approval_required(client: TestClient) -> None:
    response = client.post(
        "/task",
        json={
            "channel": "bridge_http",
            "request": {"utterance": "delete the old files"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_approval"] is True
    assert payload["response"]["status"] == TaskStatus.NEEDS_APPROVAL.value
    assert payload["response"]["approval_request"] is not None


def test_task_endpoint_rejects_missing_request(client: TestClient) -> None:
    response = client.post("/task", json={"channel": "bridge_http"})
    assert response.status_code == 422


def test_task_endpoint_does_not_require_live_ollama(client: TestClient) -> None:
    # Default fixture uses HeuristicModelProvider; this confirms the bridge
    # routes through the orchestrator without any network dependency.
    response = client.post(
        "/task",
        json={"request": {"utterance": "what time is it"}},
    )
    assert response.status_code == 200
