"""Perplexity Computer remote-client abstraction.

This module defines the typed seam EVA uses to hand work off to the
Perplexity Computer remote tier. The real network transport is out of
scope for this module — only the request/response contract and a
mockable client interface live here. A future PR can add a concrete
HTTP transport without touching callers.

Design notes
------------
- Requests carry the originating ``task_id`` so the bridge audit log can
  correlate local and remote sides of the same conversation turn.
- Responses are progress-aware (``PerplexityStatus``) so a long-running
  remote task can be reported as ``RUNNING`` without blocking the shell.
- ``needs_approval`` is surfaced on the response so the orchestrator can
  re-enter the approval flow if the remote brain proposes a high-impact
  side effect.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class PerplexityStatus(StrEnum):
    """Lifecycle states for a Perplexity Computer task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_APPROVAL = "needs_approval"
    FAILED = "failed"


class PerplexityRequest(BaseModel):
    """Outbound request to Perplexity Computer.

    The shape is deliberately small. Anything more elaborate should live
    behind a higher-level orchestrator and be reduced to these fields at
    the seam.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    utterance: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class PerplexityResponse(BaseModel):
    """Result/progress envelope returned by the remote tier."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: PerplexityStatus
    summary: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    progress: float | None = None
    needs_approval: bool = False
    error: str | None = None


@runtime_checkable
class PerplexityClient(Protocol):
    """Transport-agnostic interface for Perplexity Computer.

    A concrete HTTP client will implement this Protocol once the remote
    API surface is finalized. Until then, callers depend on this
    interface and tests inject :class:`MockPerplexityClient`.
    """

    def submit(self, request: PerplexityRequest) -> PerplexityResponse:
        """Submit ``request`` and return the current response envelope.

        Implementations may complete synchronously (returning
        ``COMPLETED``) or report an in-flight ``QUEUED``/``RUNNING``
        state for callers to poll via :meth:`status`.
        """

    def status(self, task_id: str) -> PerplexityResponse:
        """Fetch the latest envelope for an already-submitted task."""


class NoopPerplexityClient:
    """Default client used when no remote transport is configured.

    Always returns ``FAILED`` with an explanatory error. The dispatcher
    treats this as a safe degrade — the user is told the remote tier is
    unavailable rather than the request being silently dropped.
    """

    def submit(self, request: PerplexityRequest) -> PerplexityResponse:
        return PerplexityResponse(
            task_id=request.task_id,
            status=PerplexityStatus.FAILED,
            summary="Remote tier is not configured.",
            error="no_transport_configured",
        )

    def status(self, task_id: str) -> PerplexityResponse:
        return PerplexityResponse(
            task_id=task_id,
            status=PerplexityStatus.FAILED,
            summary="Remote tier is not configured.",
            error="no_transport_configured",
        )


class MockPerplexityClient:
    """In-memory client for tests and offline development.

    Behaviour is fully deterministic. Construct with a canned response or
    a callable that maps requests to responses. By default, every request
    returns a ``COMPLETED`` envelope echoing the utterance back as the
    summary.
    """

    def __init__(
        self,
        responder: PerplexityResponse | None = None,
        *,
        fail: bool = False,
        needs_approval: bool = False,
    ) -> None:
        self._canned = responder
        self._fail = fail
        self._needs_approval = needs_approval
        self.submitted: list[PerplexityRequest] = []

    def submit(self, request: PerplexityRequest) -> PerplexityResponse:
        self.submitted.append(request)
        if self._canned is not None:
            return self._canned.model_copy(update={"task_id": request.task_id})
        if self._fail:
            return PerplexityResponse(
                task_id=request.task_id,
                status=PerplexityStatus.FAILED,
                summary="Mock failure.",
                error="mock_failure",
            )
        if self._needs_approval:
            return PerplexityResponse(
                task_id=request.task_id,
                status=PerplexityStatus.NEEDS_APPROVAL,
                summary="Mock proposes a high-impact action.",
                needs_approval=True,
            )
        return PerplexityResponse(
            task_id=request.task_id,
            status=PerplexityStatus.COMPLETED,
            summary=f"[mock perplexity] {request.utterance}",
            result={"echo": request.utterance},
        )

    def status(self, task_id: str) -> PerplexityResponse:
        for req in reversed(self.submitted):
            if req.task_id == task_id:
                return self.submit(req)
        return PerplexityResponse(
            task_id=task_id,
            status=PerplexityStatus.FAILED,
            summary="Unknown task id.",
            error="unknown_task",
        )
