"""
EVA Channels — Pydantic models + domain constants.

Multi-platform publishing module that owns the transports (v1: Reddit +
Substack) behind one common ``Publisher`` Protocol. Content modules (postcards,
content-engine) can publish to any channel by composition rather than each
shipping its own transport.

Conventions match ``modules/postcards`` and ``modules/projects``: plain lists
for enum-like constants, Pydantic models for request bodies, and the service
layer returns plain dicts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Domain constants / enums (kept as plain lists to match repo convention)
# ---------------------------------------------------------------------------

# channel_items.platform — the transports shipped in v1.
PLATFORMS = ["reddit", "substack"]

# channel_items.status — publishing is irreversible, so it is approval-gated.
ITEM_STATUS = ["draft", "approved", "posted", "failed"]

# Legal transitions for an item (target -> allowed prior states).
ITEM_TRANSITIONS = {
    "approved": {"draft", "failed"},
    "posted": {"approved"},
    "failed": {"approved"},
}

# Schedule defaults (spec section 4).
DEFAULT_CADENCE_DAYS = 1

# Per-platform default config (spec section 3). Stored as one JSON row per
# platform in ``channel_platform_config`` (key = platform name).
DEFAULT_PLATFORM_CONFIG = {
    "reddit": {
        "subreddit": "",
        "username_env": "REDDIT_USERNAME",
        "password_env": "REDDIT_PASSWORD",
        "client_id_env": "REDDIT_CLIENT_ID",
        "client_secret_env": "REDDIT_CLIENT_SECRET",
        "user_agent": "Eva/0.1 by u/eva",
        "kind": "self",
    },
    "substack": {
        "publication_url": "",
        "session_env": "SUBSTACK_SESSION_COOKIE",
        "default_draft_mode": True,
    },
}


# ---------------------------------------------------------------------------
# Request payloads (API bodies) — service returns plain dicts
# ---------------------------------------------------------------------------

class ItemCreate(BaseModel):
    platform: str
    title: str
    body: str = ""
    status: str = "draft"
    payload_json: str = ""
    scheduled_at: str = ""
    actor: str = "system"


class ItemUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    payload_json: Optional[str] = None
    scheduled_at: Optional[str] = None
    actor: str = "system"


class ConfigUpdate(BaseModel):
    # Free-form per-platform key/values (e.g. subreddit, publication_url).
    values: dict = {}
    actor: str = "system"


class ScheduleUpdate(BaseModel):
    cadence_days: Optional[int] = None
    next_due: Optional[str] = None
    actor: str = "system"


class TickRequest(BaseModel):
    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
    providers: list[str]
    last_run: str
    pending_approved: int
    posted_count: int
