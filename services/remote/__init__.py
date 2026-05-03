"""Remote-tier clients for EVA's hybrid architecture.

This package houses adapters for remote brains that EVA can dispatch
work to when the local tier (LOCAL_TOOL / API_ADAPTER) is insufficient.
The primary remote tier is Perplexity Computer; see
``services/remote/perplexity.py``.

Concrete network transports are intentionally kept out of the default
build. Tests and unattended runs use a mock client.
"""

from services.remote.perplexity import (
    MockPerplexityClient,
    NoopPerplexityClient,
    PerplexityClient,
    PerplexityRequest,
    PerplexityResponse,
    PerplexityStatus,
)

__all__ = [
    "MockPerplexityClient",
    "NoopPerplexityClient",
    "PerplexityClient",
    "PerplexityRequest",
    "PerplexityResponse",
    "PerplexityStatus",
]
