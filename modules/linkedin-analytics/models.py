"""
EVA LinkedIn Analytics — Pydantic models + domain constants.

Reads LinkedIn post analytics (impressions, clicks, reactions, comments,
shares, engagement rate) for an author and stores normalized snapshots +
raw payloads in Eva's SQLite. Conventions match ``modules/projects`` and
``modules/postcards`` (freshest siblings): plain lists for enum-like
constants, Pydantic models for request bodies, and the service layer returns
plain dicts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Domain constants (kept as plain lists to match repo convention)
# ---------------------------------------------------------------------------

# analytics snapshot source — where the metrics came from.
SOURCES = ["stub", "linkedin"]

DEFAULT_ACCESS_TOKEN_ENV = "LINKEDIN_ACCESS_TOKEN"
DEFAULT_SYNC_WINDOW_DAYS = 28

# Config keys stored in the single-row-ish linkedin_sync_config key/value table.
CONFIG_KEYS = [
    "author_urn",
    "access_token_env",
    "last_sync_at",
    "sync_window_days",
    "next_due",
]


# ---------------------------------------------------------------------------
# Request payloads (API bodies) — service returns plain dicts
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    author_urn: Optional[str] = None
    access_token_env: Optional[str] = None
    sync_window_days: Optional[int] = None
    next_due: Optional[str] = None
    actor: str = "system"


class SyncRequest(BaseModel):
    actor: str = "system"


class MemoryWrite(BaseModel):
    key: str
    value: str
    source: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
    provider: str
    last_sync_at: str
    post_count: int
    snapshot_count: int
