"""
EVA Projects — Pydantic models + domain constants.

Project-tracking module that renders the whole roadmap as a collapsible
mind-map / tree in the browser (the standard way Eva tracks projects). Nodes are
stored as a tree in SQLite; every edit is recorded in an append-only ledger.

Conventions match ``modules/outreach`` and ``modules/postcards``: plain lists
for enum-like constants, Pydantic models for request bodies, and the service
layer returns plain dicts.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Domain constants / enums (kept as plain lists to match repo convention)
# ---------------------------------------------------------------------------

# project_nodes.tier — colour-coded dot in the mind-map (t1/t2/t3), or "none".
NODE_TIERS = ["t1", "t2", "t3", "none"]

# project_nodes.status — status badge in the mind-map. "" means no badge.
NODE_STATUSES = ["done", "inprog", "pending", ""]

DEFAULT_TIER = "none"
DEFAULT_STATUS = ""


# ---------------------------------------------------------------------------
# Request payloads (API bodies) — service returns plain dicts
# ---------------------------------------------------------------------------

class NodeCreate(BaseModel):
    title: str
    parent_id: Optional[str] = None
    tier: str = DEFAULT_TIER
    status: str = DEFAULT_STATUS
    meta: str = ""
    link: str = ""
    sort_order: Optional[int] = None
    actor: str = "system"


class NodeUpdate(BaseModel):
    title: Optional[str] = None
    tier: Optional[str] = None
    status: Optional[str] = None
    meta: Optional[str] = None
    link: Optional[str] = None
    sort_order: Optional[int] = None
    actor: str = "system"


class NodeMove(BaseModel):
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    actor: str = "system"


class TreeNode(BaseModel):
    """One node in an import/export tree (nested, ``children`` optional)."""

    title: str
    tier: str = DEFAULT_TIER
    status: str = DEFAULT_STATUS
    meta: str = ""
    link: str = ""
    children: List["TreeNode"] = []


class ImportRequest(BaseModel):
    nodes: List[TreeNode]
    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str


TreeNode.model_rebuild()
