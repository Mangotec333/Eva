"""EVA/EVE communication protocol contracts.

The protocol package defines the typed envelopes that flow between the voice
shell, the bridge/API, the brain orchestrator, and any external clients. The
package is intentionally framework-free: anything that imports from
``services.protocols`` should not need FastAPI, httpx, or Ollama present.
"""

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

__all__ = [
    "PROTOCOL_VERSION",
    "ApprovalDecision",
    "ApprovalEvent",
    "BrainResponseEnvelope",
    "Capability",
    "CapabilitiesResponse",
    "Channel",
    "HealthStatus",
    "ProtocolDescriptor",
    "ProtocolListResponse",
    "ProtocolStatus",
    "TaskRequestEnvelope",
]
