"""
EVA Shopify — FastAPI microservice
===================================
Port: 8788

Order sync + inventory + dropshipping fulfillment for Vineet's Shopify store.

Design (per EVA Architecture Directive):
  * All Shopify Admin API I/O lives behind a ``ShopifyClient`` Protocol with an
    offline ``StubShopifyClient`` — so this runs (and tests) with zero network
    and no live credentials.
  * READ paths (order sync, inventory read) are safe and direct.
  * WRITE paths that touch the live store (order fulfillment status update,
    inventory level set) are irreversible and therefore ALWAYS go through the
    approval gate: request -> pending_approval -> approve (executes) / reject.
  * Dropshipping "fulfill new order" = forward the order to a config-driven
    supplier/partner notifier (stub | webhook | email). Never hardcodes a vendor.
  * Own SQLite with a per-agent ``memory`` table and an append-only ``ledger``.

Nothing about a real store is hardcoded. Until the user supplies a store domain
+ Admin API token (see README), the service runs in offline stub mode and the
live-write execution reports ``not_connected`` rather than guessing.

Endpoints:
  POST /sync                       Pull recent orders into local storage
  GET  /orders                     List synced orders (optional ?fulfillment_status=)
  GET  /orders/{id}                Get a synced order
  POST /orders/{id}/forward        Forward order to supplier (dropship fulfill)
  POST /orders/{id}/fulfill        Request live fulfillment update (-> approval)
  GET  /inventory                  Read current inventory levels
  POST /inventory/set              Request a live inventory change (-> approval)
  GET  /approvals                  List approvals (optional ?status=)
  GET  /approvals/{id}             Get an approval
  POST /approvals/{id}/approve     Approve + execute the live write
  POST /approvals/{id}/reject      Reject a pending approval
  GET  /memory                     List agent memory
  POST /memory                     Set an agent memory key
  GET  /ledger                     Query the append-only ledger
  GET  /ledger/export              Export the ledger (csv|json)
  GET  /health                     Health check
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import database as db
from config import load_config
from models import (
    ApprovalDecision,
    ForwardRequest,
    FulfillRequest,
    HealthResponse,
    InventorySetRequest,
    MemorySet,
    SyncRequest,
)
from service import NotFoundError, ShopifyService, ShopifyServiceError

VERSION = "1.0.0"

service = ShopifyService()

app = FastAPI(
    title="EVA Shopify",
    description=(
        "Order sync + inventory + dropshipping fulfillment for Shopify. Live "
        "writes are approval-gated; all Admin API I/O is behind a Protocol with "
        "an offline stub."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn):
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ShopifyServiceError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    cfg = service.config
    return HealthResponse(
        status="ok",
        module="eva-shopify",
        version=VERSION,
        db=db.DB_PATH,
        live_ready=cfg.is_live_ready,
        shopify_client=service.client.name,
        fulfillment_mode=service.notifier.name,
        missing_for_live=cfg.missing_for_live(),
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@app.post("/sync", tags=["Orders"])
def sync_orders(payload: SyncRequest = SyncRequest()):
    return _handle(lambda: service.sync_orders(
        since=payload.since, status=payload.status, actor=payload.actor))


@app.get("/orders", tags=["Orders"])
def list_orders(fulfillment_status: Optional[str] = Query(default=None)):
    rows = service.list_orders(fulfillment_status=fulfillment_status)
    return {"orders": rows, "count": len(rows)}


@app.get("/orders/{order_id}", tags=["Orders"])
def get_order(order_id: str):
    return _handle(lambda: service.get_order(order_id))


@app.post("/orders/{order_id}/forward", tags=["Orders"])
def forward_order(order_id: str, payload: ForwardRequest = ForwardRequest()):
    return _handle(lambda: service.forward_order(order_id, actor=payload.actor))


@app.post("/orders/{order_id}/fulfill", status_code=201, tags=["Orders"])
def request_fulfillment(order_id: str, payload: FulfillRequest = FulfillRequest()):
    body = payload.model_dump()
    actor = body.pop("actor", "api")
    return _handle(lambda: service.request_fulfillment(order_id, body, actor=actor))


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@app.get("/inventory", tags=["Inventory"])
def get_inventory():
    return _handle(lambda: service.get_inventory())


@app.post("/inventory/set", status_code=201, tags=["Inventory"])
def request_set_inventory(payload: InventorySetRequest):
    return _handle(lambda: service.request_set_inventory(
        payload.inventory_item_id, payload.location_id,
        payload.available, actor=payload.actor))


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

@app.get("/approvals", tags=["Approvals"])
def list_approvals(status: Optional[str] = Query(default=None)):
    rows = service.list_approvals(status=status)
    return {"approvals": rows, "count": len(rows)}


@app.get("/approvals/{approval_id}", tags=["Approvals"])
def get_approval(approval_id: str):
    return _handle(lambda: service.get_approval(approval_id))


@app.post("/approvals/{approval_id}/approve", tags=["Approvals"])
def approve(approval_id: str, payload: ApprovalDecision = ApprovalDecision()):
    return _handle(lambda: service.approve(approval_id, approved_by=payload.approved_by))


@app.post("/approvals/{approval_id}/reject", tags=["Approvals"])
def reject(approval_id: str, payload: ApprovalDecision = ApprovalDecision()):
    return _handle(lambda: service.reject(approval_id, approved_by=payload.approved_by))


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@app.get("/memory", tags=["Memory"])
def list_memory():
    rows = service.list_memory()
    return {"memory": rows, "count": len(rows)}


@app.post("/memory", tags=["Memory"])
def set_memory(payload: MemorySet):
    return service.set_memory(payload.key, payload.value, source=payload.source)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@app.get("/ledger", tags=["Ledger"])
def query_ledger(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
):
    rows = service.query_ledger(from_ts=from_, to_ts=to, event_type=event_type)
    return {"ledger": rows, "count": len(rows)}


@app.get("/ledger/export", tags=["Ledger"])
def export_ledger(format: str = Query(default="json")):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=422, detail="format must be csv or json")
    body = service.export_ledger(format)
    media = "text/csv" if format == "csv" else "application/json"
    return PlainTextResponse(content=body, media_type=media)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Shopify microservice")
    parser.add_argument("--port", type=int, default=8788, help="Port (default: 8788)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
