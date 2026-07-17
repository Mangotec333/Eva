"""
EVA Treasurer — FastAPI microservice
=====================================
Port: 8786

Treasurer tracks all Eva operational spend (API/LLM credits, subscriptions,
marketplace fees, ad spend, deal costs, hosting/domains) vs per-category budget
caps so Vineet always knows the burn rate. Tight, lean, stdlib-only — no bank
integrations yet.

Endpoints:
  GET  /health          Health + tracked-categories + offline flag
  POST /finance/track    Log a spend event
  GET  /finance/summary  Spend by category for a period (?period=day|week|month)
  GET  /finance/budget   Budget caps vs actual (per category usage)
  POST /finance/budget   Set / update a category cap
  GET  /finance/export   CSV dump of all spend events
  GET  /finance/burn     Current-month run-rate projection vs budget

Offline-safe: with ``EVA_TREASURER_OFFLINE=1`` (default in the sandbox), the
state writes use a stub and no Slack/ledger network is fired.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import finance_tracker as core
from service import TreasurerService

AGENT_VERSION = "0.1.0"
PORT = 8786

service = TreasurerService()

app = FastAPI(
    title="EVA Treasurer",
    description=(
        "Finance tracker: logs all Eva operational spend (API/LLM credits, "
        "subscriptions, marketplace fees, ad spend, deal costs, hosting) vs "
        "per-category budget caps, alerts on threshold breach, and projects "
        "the monthly burn rate. Stdlib-only, no bank integrations."
    ),
    version=AGENT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SpendIn(BaseModel):
    category: str
    amount_cents: int
    vendor: Optional[str] = ""
    source_agent: Optional[str] = ""
    note: Optional[str] = ""
    timestamp: Optional[str] = None
    event_key: Optional[str] = None


class BudgetIn(BaseModel):
    category: str
    cap_cents: int
    period: Optional[str] = "month"


class SpendRequestIn(BaseModel):
    category: str
    amount_cents: int
    vendor: Optional[str] = ""
    source_agent: Optional[str] = ""
    note: Optional[str] = ""


class ApprovalIn(BaseModel):
    actor: Optional[str] = "launcher"
    via: Optional[str] = "endpoint"


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-treasurer",
        "version": AGENT_VERSION,
        "port": PORT,
        "db": service.db_path,
        "offline": os.environ.get("EVA_TREASURER_OFFLINE") == "1",
        "categories": core.CATEGORIES,
    }


@app.post("/finance/track", tags=["Finance"])
async def finance_track(body: SpendIn):
    """Log a spend event; alerts if it crosses its category budget threshold."""
    result = service.track(
        category=body.category, amount_cents=body.amount_cents,
        vendor=body.vendor or "", source_agent=body.source_agent or "",
        note=body.note or "", timestamp=body.timestamp,
        event_key=body.event_key)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "bad request"))
    return result


@app.get("/finance/summary", tags=["Finance"])
async def finance_summary(period: str = "month"):
    """Spend by category for the period (day / week / month)."""
    return service.summary(period)


@app.get("/finance/budget", tags=["Finance"])
async def finance_budget(period: Optional[str] = None):
    """Budget caps vs actual, with per-category usage status."""
    return service.budget(period)


@app.post("/finance/budget", tags=["Finance"])
async def finance_set_budget(body: BudgetIn):
    """Set / update a category's budget cap."""
    result = service.set_budget(
        category=body.category, cap_cents=body.cap_cents,
        period=body.period or "month")
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "bad request"))
    return result


@app.get("/finance/export", tags=["Finance"], response_class=PlainTextResponse)
async def finance_export():
    """CSV dump of every spend event."""
    return PlainTextResponse(content=service.export_csv(), media_type="text/csv")


@app.get("/finance/burn", tags=["Finance"])
async def finance_burn():
    """Current-month run-rate projection vs total monthly budget."""
    return service.burn()


@app.post("/finance/request", tags=["Approval"])
async def finance_request_spend(body: SpendRequestIn):
    """Record a spend awaiting approval. Nothing is logged until approved."""
    result = service.request_spend(
        category=body.category, amount_cents=body.amount_cents,
        vendor=body.vendor or "", source_agent=body.source_agent or "",
        note=body.note or "")
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "bad request"))
    return result


@app.get("/finance/pending", tags=["Approval"])
async def finance_pending(status: Optional[str] = None):
    """List spend requests (optionally filtered by status)."""
    return service.list_pending_spends(status=status)


@app.post("/finance/approve/{request_id}", tags=["Approval"])
async def finance_approve_spend(request_id: str, body: ApprovalIn = Body(default=ApprovalIn())):
    """Approve a pending spend and commit it to the ledger."""
    result = service.approve_spend(request_id, actor=body.actor or "launcher",
                                   via=body.via or "endpoint")
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "cannot approve"))
    return result


@app.post("/finance/reject/{request_id}", tags=["Approval"])
async def finance_reject_spend(request_id: str, body: ApprovalIn = Body(default=ApprovalIn())):
    """Reject a pending spend so it is never logged."""
    result = service.reject_spend(request_id, actor=body.actor or "launcher")
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "cannot reject"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Treasurer finance tracker")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
