from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from services.brain.schema import BrainResponse, TaskRequest, TaskStatus
from services.protocols.contracts import (
    PROTOCOL_VERSION,
    ApprovalDecision,
    ApprovalEvent,
    BrainResponseEnvelope,
    Capability,
    CapabilitiesResponse,
    Channel,
    HealthStatus,
    ProtocolDescriptor,
    ProtocolListResponse,
    ProtocolStatus,
    TaskRequestEnvelope,
)


def test_protocol_version_constant() -> None:
    assert PROTOCOL_VERSION == "0.1.0"


def test_task_request_envelope_defaults() -> None:
    request = TaskRequest(utterance="hello eva")
    envelope = TaskRequestEnvelope(request=request)
    assert envelope.protocol_version == PROTOCOL_VERSION
    assert envelope.channel == Channel.BRIDGE_HTTP
    assert envelope.request.utterance == "hello eva"


def test_task_request_envelope_round_trip_json() -> None:
    request = TaskRequest(utterance="hello eva", source="text")
    envelope = TaskRequestEnvelope(channel=Channel.TEXT, request=request)
    payload = envelope.model_dump_json()
    parsed = TaskRequestEnvelope.model_validate_json(payload)
    assert parsed.channel == Channel.TEXT
    assert parsed.request.utterance == "hello eva"
    assert parsed.protocol_version == PROTOCOL_VERSION


def test_task_request_envelope_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TaskRequestEnvelope.model_validate(
            {
                "request": {"utterance": "hi"},
                "rogue": "nope",
            }
        )


def test_brain_response_envelope_marks_approval_required() -> None:
    response = BrainResponse(
        task_id="abc",
        status=TaskStatus.NEEDS_APPROVAL,
        spoken_summary="needs approval",
        text="needs approval",
        approval_request={"reason": "side effect"},
    )
    envelope = BrainResponseEnvelope.from_response(response)
    assert envelope.requires_approval is True
    assert envelope.response.task_id == "abc"


def test_brain_response_envelope_safe_response() -> None:
    response = BrainResponse(
        task_id="abc",
        status=TaskStatus.COMPLETED,
        spoken_summary="ok",
        text="ok",
    )
    envelope = BrainResponseEnvelope.from_response(response)
    assert envelope.requires_approval is False
    assert envelope.protocol_version == PROTOCOL_VERSION


def test_approval_event_validates_decision() -> None:
    event = ApprovalEvent(task_id="abc", decision=ApprovalDecision.APPROVED)
    assert event.decision == ApprovalDecision.APPROVED
    assert event.approver == "local-user"
    assert event.event_id  # default-generated

    with pytest.raises(ValidationError):
        ApprovalEvent(task_id="abc", decision="maybe")  # type: ignore[arg-type]


def test_protocol_status_serializes() -> None:
    status = ProtocolStatus(
        started_at=datetime(2026, 5, 2, 12, 0, 0),
        model_provider="HeuristicModelProvider",
    )
    assert status.status == HealthStatus.OK
    payload = status.model_dump()
    assert payload["model_provider"] == "HeuristicModelProvider"


def test_protocol_list_response_holds_descriptors() -> None:
    listing = ProtocolListResponse(
        protocols=[
            ProtocolDescriptor(
                name="task.http",
                transport="http",
                description="POST /task",
            )
        ]
    )
    assert listing.protocols[0].name == "task.http"
    assert listing.protocols[0].status == HealthStatus.OK


def test_capabilities_response_fields() -> None:
    caps = CapabilitiesResponse(
        model_provider="HeuristicModelProvider",
        capabilities=[
            Capability(name="answer.text", description="answer"),
            Capability(
                name="approval.required",
                description="needs approval",
                requires_approval=True,
            ),
        ],
    )
    assert {c.name for c in caps.capabilities} == {"answer.text", "approval.required"}
    assert caps.capabilities[1].requires_approval is True
