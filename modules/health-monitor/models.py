"""
EVA Health Monitor — Pydantic models for the FastAPI surface.

The service returns plain dicts (matching postcards/outreach); these models only
describe request bodies and the health response.
"""

from __future__ import annotations

from pydantic import BaseModel


class TickRequest(BaseModel):
    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
    client: str
    monitored: int
    failure_threshold: int
    last_run: dict
