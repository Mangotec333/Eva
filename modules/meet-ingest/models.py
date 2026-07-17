"""
EVA Meet Ingest — Pydantic models for the FastAPI surface.

The service returns plain dicts (matching postcards/outreach); these models only
describe request bodies and the health response.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PollRequest(BaseModel):
    actor: str = "system"


class ProcessRequest(BaseModel):
    actor: str = "system"


class TickRequest(BaseModel):
    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
    drive: str
    transcriber: str
    last_run: dict
