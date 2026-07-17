"""
EVA Shopify — Pydantic models + domain constants.

Request/response bodies for the FastAPI surface. The service layer returns plain
dicts (matching the postcards/outreach convention); these models validate input
and document the API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# Live-write actions that must pass through the approval gate before they touch a
# real Shopify store. Read paths (order sync, inventory read) are never gated.
ACTION_FULFILL_ORDER = "fulfill_order"
ACTION_SET_INVENTORY = "set_inventory"
GATED_ACTIONS = [ACTION_FULFILL_ORDER, ACTION_SET_INVENTORY]


class SyncRequest(BaseModel):
    since: str = ""
    status: str = "any"
    actor: str = "system"


class FulfillRequest(BaseModel):
    """Request a fulfillment for a synced order. Creates a pending approval;
    the live write only happens once approved."""

    status: str = "fulfilled"
    tracking_number: str = ""
    tracking_company: str = ""
    tracking_url: str = ""
    actor: str = "system"


class InventorySetRequest(BaseModel):
    inventory_item_id: str
    location_id: str
    available: int
    actor: str = "system"


class ApprovalDecision(BaseModel):
    approved_by: str = "founder"


class ForwardRequest(BaseModel):
    """Forward a synced order to the configured supplier/fulfillment partner."""

    actor: str = "system"


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
    live_ready: bool
    shopify_client: str
    fulfillment_mode: str
    missing_for_live: list[str] = []


class MemorySet(BaseModel):
    key: str
    value: str
    source: str = "api"
