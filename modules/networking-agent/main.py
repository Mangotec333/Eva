"""
EVA Networking-Agent — FastAPI microservice
============================================
Port: 8793  (sibling lobe to brand-builder :8792)

Two integrated layers over one store + one approval loop:
  * Layer A — Relationship Capital (contacts): stage model + next-best-action.
  * Layer B — Community Scout (groups): discover → score → engage → learn.

Guardrail: all outbound content (post/comment/connection_request/dm) is
draft-and-approve only. Only ``join_public_group`` and ``monitor_keyword_mention``
run autonomously (and are still logged to the append-only outcomes ledger).

Endpoints:
  GET  /status                       Module status
  GET  /directives/{venture}         Resolved ICP/offer/voice for a venture
  POST /plan/{venture}               Directive-aware plan (stages + next actions)
  POST /groups/discover              Ingest a seed list (ManualSeedProvider)
  GET  /groups                       List groups (filter venture/platform/status)
  GET  /groups/{id}                  Get one group
  POST /groups/{id}/score            (Re)score a group
  POST /groups/{id}/draft            Draft outbound content (approval-gated)
  POST /groups/{id}/approve          Approve a draft
  POST /groups/{id}/send             Send/post an approved draft
  POST /groups/{id}/auto-action      Whitelisted autonomous action
  POST /groups/{id}/log-outcome      Log a KAIZEN outcome signal
  GET  /contacts                     List contacts (Layer A)
  POST /kaizen/reweight              Run the KAIZEN reweighting loop
  GET  /docs                         OpenAPI docs (FastAPI built-in)
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from service import NetworkingAgentService

VERSION = "1.0.0"
PORT = 8793

service = NetworkingAgentService()

app = FastAPI(
    title="EVA Networking-Agent (Relationship Capital + Community Scout)",
    description=(
        "Layer A relationship-capital tracking + Layer B community discovery/"
        "scoring over one store and one approval loop. Outbound content is "
        "draft-and-approve only; only join_public_group and "
        "monitor_keyword_mention run autonomously."
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


class DiscoverIn(BaseModel):
    venture: str
    seed_data: Optional[object] = None
    provider: str = "manual_seed"


class DraftIn(BaseModel):
    entity_type: str = "group"
    content: str
    action: str = "post"


class ApproveIn(BaseModel):
    approved_by: str = "founder"


class SendIn(BaseModel):
    actor: str = "system"


class AutoActionIn(BaseModel):
    action: str
    entity_type: str = "group"
    actor: str = "auto"


class LogOutcomeIn(BaseModel):
    entity_type: str = "group"
    outcome: str
    signal: str = ""
    actor: str = "system"


@app.get("/status", tags=["Meta"])
def status():
    return service.status()


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "module": "eva-networking-agent",
            "version": VERSION, "port": PORT, "offline": service.offline}


@app.get("/directives/{venture}", tags=["Directives"])
def get_directive(venture: str):
    return service.get_directive(venture)


@app.post("/plan/{venture}", tags=["Planning"])
def plan(venture: str):
    return service.plan(venture)


@app.post("/groups/discover", tags=["Groups"])
def discover(body: DiscoverIn):
    return service.discover(body.venture, body.seed_data, provider=body.provider)


@app.get("/groups", tags=["Groups"])
def list_groups(
    venture: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    rows = service.list_groups(venture=venture, platform=platform, status=status)
    return {"groups": rows, "count": len(rows)}


@app.get("/groups/{group_id}", tags=["Groups"])
def get_group(group_id: str):
    group = service.get_group(group_id)
    if not group:
        return {"ok": False, "error": f"group {group_id!r} not found", "code": "not_found"}
    return group


@app.post("/groups/{group_id}/score", tags=["Groups"])
def score_group(group_id: str):
    return service.score(group_id)


@app.post("/groups/{group_id}/draft", tags=["Approval loop"])
def draft(group_id: str, body: DraftIn):
    return service.draft(body.entity_type, group_id, body.content, action=body.action)


@app.post("/groups/{group_id}/approve", tags=["Approval loop"])
def approve(group_id: str, draft_id: str = Query(...), body: ApproveIn = ApproveIn()):
    return service.approve(draft_id, approved_by=body.approved_by)


@app.post("/groups/{group_id}/send", tags=["Approval loop"])
def send(group_id: str, draft_id: str = Query(...), body: SendIn = SendIn()):
    return service.send(draft_id, actor=body.actor)


@app.post("/groups/{group_id}/auto-action", tags=["Autonomy"])
def auto_action(group_id: str, body: AutoActionIn):
    return service.auto_action(body.action, group_id,
                               entity_type=body.entity_type, actor=body.actor)


@app.post("/groups/{group_id}/log-outcome", tags=["KAIZEN"])
def log_outcome(group_id: str, body: LogOutcomeIn):
    return service.log_outcome(body.entity_type, group_id, body.outcome,
                               signal=body.signal, actor=body.actor)


@app.get("/contacts", tags=["Contacts (Layer A)"])
def list_contacts(
    venture: Optional[str] = Query(default=None),
    stage: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    rows = service.list_contacts(venture=venture, stage=stage, status=status)
    return {"contacts": rows, "count": len(rows)}


@app.post("/kaizen/reweight", tags=["KAIZEN"])
def kaizen_reweight():
    return service.kaizen_reweight()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Networking-Agent microservice")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
