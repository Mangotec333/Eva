from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_APPROVAL = "needs_approval"
    SCHEDULED = "scheduled"
    FAILED_SAFE = "failed_safe"


class TaskRequest(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = "voice"
    utterance: str
    timestamp: datetime = Field(default_factory=datetime.now)
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class BrainResponse(BaseModel):
    task_id: str
    status: TaskStatus
    spoken_summary: str
    text: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    approval_request: dict[str, Any] | None = None
    audit_trace_id: str = Field(default_factory=lambda: str(uuid4()))

