from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from services.brain.orchestrator import BrainOrchestrator
from services.model.provider import HeuristicModelProvider, ModelProvider
from services.protocols.contracts import (
    PROTOCOL_VERSION,
    BrainResponseEnvelope,
    Capability,
    CapabilitiesResponse,
    HealthStatus,
    ProtocolDescriptor,
    ProtocolListResponse,
    ProtocolStatus,
    TaskRequestEnvelope,
)


def _default_capabilities() -> list[Capability]:
    return [
        Capability(
            name="answer.text",
            description="Answer a safe natural-language question via the brain orchestrator.",
        ),
        Capability(
            name="approval.required",
            description="Detect high-impact requests and surface them for explicit approval.",
            requires_approval=True,
        ),
        Capability(
            name="health.report",
            description="Expose protocol/bridge health for local diagnostics.",
        ),
    ]


def _default_protocols() -> list[ProtocolDescriptor]:
    return [
        ProtocolDescriptor(
            name="task.http",
            transport="http",
            description="POST /task — submit a TaskRequestEnvelope, receive a BrainResponseEnvelope.",
        ),
        ProtocolDescriptor(
            name="health.http",
            transport="http",
            description="GET /health — liveness and protocol version.",
        ),
        ProtocolDescriptor(
            name="capabilities.http",
            transport="http",
            description="GET /capabilities — advertise capability surface.",
        ),
        ProtocolDescriptor(
            name="events.sse",
            transport="sse",
            description="GET /events — minimal server-sent event skeleton (heartbeat only).",
            status=HealthStatus.DEGRADED,
        ),
    ]


def build_app(
    *,
    model_provider: ModelProvider | None = None,
    started_at: datetime | None = None,
) -> FastAPI:
    return create_app(model_provider=model_provider, started_at=started_at)


def create_app(
    *,
    model_provider: ModelProvider | None = None,
    started_at: datetime | None = None,
) -> FastAPI:
    provider = model_provider or HeuristicModelProvider()
    brain = BrainOrchestrator(provider)
    boot_time = started_at or datetime.now()
    provider_name = type(provider).__name__

    app = FastAPI(
        title="EVA Bridge",
        version=PROTOCOL_VERSION,
        description=(
            "Local-first bridge for the EVA/EVE assistant. "
            "Bind to 127.0.0.1 only — do not expose without an auth layer."
        ),
    )

    app.state.model_provider = provider
    app.state.brain = brain
    app.state.started_at = boot_time

    @app.get("/health", response_model=ProtocolStatus)
    async def health() -> ProtocolStatus:
        return ProtocolStatus(
            status=HealthStatus.OK,
            started_at=boot_time,
            model_provider=provider_name,
            notes="Local-only bridge. Approval-required tasks are surfaced explicitly.",
        )

    @app.get("/protocols", response_model=ProtocolListResponse)
    async def protocols() -> ProtocolListResponse:
        return ProtocolListResponse(protocols=_default_protocols())

    @app.get("/capabilities", response_model=CapabilitiesResponse)
    async def capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse(
            model_provider=provider_name,
            capabilities=_default_capabilities(),
        )

    @app.post("/task", response_model=BrainResponseEnvelope)
    async def submit_task(envelope: TaskRequestEnvelope) -> BrainResponseEnvelope:
        response = await brain.handle(envelope.request)
        return BrainResponseEnvelope.from_response(response, channel=envelope.channel)

    @app.get("/events")
    async def events() -> StreamingResponse:
        async def stream():
            yield (
                f"event: ready\ndata: {{\"protocol_version\": \"{PROTOCOL_VERSION}\"}}\n\n"
            )
            try:
                while True:
                    await asyncio.sleep(15)
                    yield "event: heartbeat\ndata: {}\n\n"
            except asyncio.CancelledError:  # pragma: no cover - client disconnect
                return

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


__all__ = ["build_app", "create_app"]
