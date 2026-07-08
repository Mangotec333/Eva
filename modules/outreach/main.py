"""
EVA Outreach & Investor Verification — FastAPI microservice
===========================================================
Port: 8768  (deal-scout 8766, deal-analyzer 8767)

Approval-gated outreach send queue + accredited-investor verification + global
suppression list + append-only compliance ledger. No email is transmitted in
v1: approved messages are handed to a pluggable ``sender`` (stub logger).

Endpoints (spec section 5):
  POST   /contacts                                   Create a contact
  GET    /contacts                                   List contacts
  GET    /contacts/{id}                              Get a contact
  PATCH  /contacts/{id}                              Update a contact
  POST   /campaigns                                  Create a campaign
  GET    /campaigns                                  List campaigns
  GET    /campaigns/{id}                             Get a campaign
  POST   /campaigns/{id}/recipients                  Add recipients (suppressed excluded)
  POST   /campaigns/{id}/recipients/{rid}/approve    Human approval
  POST   /campaigns/{id}/recipients/{rid}/deny       Deny
  POST   /campaigns/{id}/recipients/{rid}/send       Send (approved + not suppressed)
  POST   /suppression                                Record opt-out
  GET    /suppression/check?email=                   Suppression check
  POST   /verifications                              Create verification case
  GET    /verifications                              List verification cases
  PATCH  /verifications/{id}                          Advance verification state
  POST   /sales                                      Record a sale (506(c) gated)
  GET    /ledger?from=&to=&event_type=               Query compliance ledger
  GET    /ledger/export?format=csv|json              Export ledger
  GET    /health                                     Health check
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import database as db
from models import (
    ApproveRequest,
    CampaignCreate,
    ContactCreate,
    ContactUpdate,
    DenyRequest,
    EvidenceCreate,
    FilingReminderCreate,
    HealthResponse,
    RecipientAdd,
    SaleRequest,
    SendRequest,
    SuppressionCreate,
    VerificationCreate,
    VerificationUpdate,
)
from service import ComplianceError, NotFoundError, OutreachService

VERSION = "1.0.0"

service = OutreachService()

app = FastAPI(
    title="EVA Outreach & Investor Verification",
    description=(
        "Approval-gated outreach send queue, accredited-investor verification "
        "workflow, global suppression list, and append-only compliance ledger."
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
    """Translate domain exceptions into HTTP errors."""
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ComplianceError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    return HealthResponse(status="ok", module="eva-outreach", version=VERSION, db=db.DB_PATH)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@app.post("/contacts", status_code=201, tags=["Contacts"])
def create_contact(payload: ContactCreate):
    return _handle(lambda: service.add_contact(payload.model_dump()))


@app.get("/contacts", tags=["Contacts"])
def list_contacts(
    relationship_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    rows = service.list_contacts(relationship_type=relationship_type, status=status)
    return {"contacts": rows, "count": len(rows)}


@app.get("/contacts/{contact_id}", tags=["Contacts"])
def get_contact(contact_id: str):
    return _handle(lambda: service.get_contact(contact_id))


@app.patch("/contacts/{contact_id}", tags=["Contacts"])
def update_contact(contact_id: str, payload: ContactUpdate):
    return _handle(
        lambda: service.update_contact(contact_id, payload.model_dump(exclude_none=True))
    )


@app.post("/contacts/{contact_id}/evidence", status_code=201, tags=["Contacts"])
def add_evidence(contact_id: str, payload: EvidenceCreate):
    return _handle(lambda: service.add_relationship_evidence(contact_id, payload.note))


# ---------------------------------------------------------------------------
# Campaigns + recipients
# ---------------------------------------------------------------------------

@app.post("/campaigns", status_code=201, tags=["Campaigns"])
def create_campaign(payload: CampaignCreate):
    return _handle(lambda: service.create_campaign(payload.model_dump()))


@app.get("/campaigns", tags=["Campaigns"])
def list_campaigns():
    rows = service.list_campaigns()
    return {"campaigns": rows, "count": len(rows)}


@app.get("/campaigns/{campaign_id}", tags=["Campaigns"])
def get_campaign(campaign_id: str):
    campaign = _handle(lambda: service.get_campaign(campaign_id))
    recipients = service.list_recipients(campaign_id=campaign_id)
    return {"campaign": campaign, "recipients": recipients}


@app.post("/campaigns/{campaign_id}/recipients", status_code=201, tags=["Campaigns"])
def add_recipients(campaign_id: str, payload: RecipientAdd):
    return _handle(
        lambda: service.add_recipients(campaign_id, payload.contact_ids, payload.actor)
    )


@app.post("/campaigns/{campaign_id}/recipients/{rid}/approve", tags=["Campaigns"])
def approve_recipient(campaign_id: str, rid: str, payload: ApproveRequest):
    return _handle(lambda: service.approve_recipient(rid, payload.approved_by))


@app.post("/campaigns/{campaign_id}/recipients/{rid}/deny", tags=["Campaigns"])
def deny_recipient(campaign_id: str, rid: str, payload: DenyRequest):
    return _handle(lambda: service.deny_recipient(rid, payload.actor, payload.reason))


@app.post("/campaigns/{campaign_id}/recipients/{rid}/send", tags=["Campaigns"])
def send_recipient(campaign_id: str, rid: str, payload: SendRequest = SendRequest()):
    return _handle(lambda: service.send_recipient(rid, payload.actor))


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------

@app.post("/suppression", status_code=201, tags=["Suppression"])
def add_suppression(payload: SuppressionCreate):
    return _handle(
        lambda: service.add_suppression(
            payload.email, payload.reason, payload.source, payload.actor
        )
    )


@app.get("/suppression/check", tags=["Suppression"])
def check_suppression(email: str = Query(...)):
    return service.check_suppression(email)


@app.get("/suppression", tags=["Suppression"])
def list_suppression():
    rows = service.list_suppression()
    return {"suppression": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@app.post("/verifications", status_code=201, tags=["Verification"])
def create_verification(payload: VerificationCreate):
    return _handle(
        lambda: service.create_verification(
            payload.contact_id, payload.method, payload.notes, payload.actor
        )
    )


@app.get("/verifications", tags=["Verification"])
def list_verifications(
    contact_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    rows = service.list_verifications(contact_id=contact_id, status=status)
    return {"verifications": rows, "count": len(rows)}


@app.patch("/verifications/{case_id}", tags=["Verification"])
def advance_verification(case_id: str, payload: VerificationUpdate):
    return _handle(
        lambda: service.advance_verification(
            case_id, payload.status, payload.verifier,
            payload.documents_ref, payload.notes, payload.actor,
        )
    )


# ---------------------------------------------------------------------------
# Sales (506(c) gate)
# ---------------------------------------------------------------------------

@app.post("/sales", status_code=201, tags=["Sales"])
def record_sale(payload: SaleRequest):
    return _handle(
        lambda: service.record_sale(
            payload.contact_id, payload.amount, payload.actor, payload.notes
        )
    )


# ---------------------------------------------------------------------------
# Compliance ledger
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
# Filing reminders
# ---------------------------------------------------------------------------

@app.post("/filing-reminders", status_code=201, tags=["Filing"])
def add_filing_reminder(payload: FilingReminderCreate):
    return _handle(lambda: service.add_filing_reminder(payload.model_dump()))


@app.get("/filing-reminders", tags=["Filing"])
def list_filing_reminders():
    rows = service.list_filing_reminders()
    return {"filing_reminders": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Outreach microservice")
    parser.add_argument("--port", type=int, default=8768, help="Port (default: 8768)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
