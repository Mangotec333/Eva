from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from services.brain.schema import BrainResponse, TaskRequest, TaskStatus

PROTOCOL_VERSION = "0.1.0"


class Channel(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    BRIDGE_HTTP = "bridge_http"
    BRIDGE_WS = "bridge_ws"
    SYSTEM = "system"


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class TaskRequestEnvelope(BaseModel):
    """Outer envelope for a task request flowing into the brain."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    channel: Channel = Channel.BRIDGE_HTTP
    source: str = "bridge"
    request: TaskRequest


class BrainResponseEnvelope(BaseModel):
    """Outer envelope for a brain response delivered back to a caller."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    channel: Channel = Channel.BRIDGE_HTTP
    requires_approval: bool = False
    response: BrainResponse

    @classmethod
    def from_response(
        cls,
        response: BrainResponse,
        channel: Channel = Channel.BRIDGE_HTTP,
    ) -> "BrainResponseEnvelope":
        return cls(
            channel=channel,
            requires_approval=response.status == TaskStatus.NEEDS_APPROVAL,
            response=response,
        )


class ApprovalEvent(BaseModel):
    """User-side approval/denial for a task that requested approval."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    decision: ApprovalDecision
    reason: str | None = None
    decided_at: datetime = Field(default_factory=datetime.now)
    approver: str = "local-user"


class ProtocolDescriptor(BaseModel):
    """Description of a single transport/protocol the bridge advertises."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = PROTOCOL_VERSION
    transport: str
    description: str
    status: HealthStatus = HealthStatus.OK


class ProtocolListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    protocols: list[ProtocolDescriptor]


class ProtocolStatus(BaseModel):
    """Health/status payload returned by `GET /health`."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    status: HealthStatus = HealthStatus.OK
    started_at: datetime
    now: datetime = Field(default_factory=datetime.now)
    model_provider: str
    notes: str | None = None


class Capability(BaseModel):
    """A single capability advertised by the bridge."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    requires_approval: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    model_provider: str
    capabilities: list[Capability]
