"""
EVA Outreach & Investor Verification — Pydantic models + domain constants.

Module 6 of the EVA system. Approval-gated outreach send queue, accredited-
investor verification workflow, global suppression list, and an append-only
compliance ledger for the SEC Form D / blue-sky paper trail.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Domain constants / enums (kept as plain lists to match repo convention)
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES = ["warm", "cold"]

# campaign_recipients.status
RECIPIENT_STATUS = [
    "pending_approval",
    "approved",
    "denied",
    "sent",
    "failed",
    "suppressed",
]

# verification_cases.status
VERIFICATION_STATUS = [
    "requested",
    "documents_received",
    "verified",
    "rejected",
    "expired",
]

# Legal transitions for a verification case (target -> allowed prior states).
VERIFICATION_TRANSITIONS = {
    "documents_received": {"requested"},
    "verified": {"requested", "documents_received"},
    "rejected": {"requested", "documents_received"},
    "expired": {"verified"},
}

# Accredited-investor verification is valid for one year (SEC re-verify annually).
VERIFICATION_TTL_DAYS = 365


# ---------------------------------------------------------------------------
# Request payloads (API bodies) — service returns plain dicts
# ---------------------------------------------------------------------------

class ContactCreate(BaseModel):
    email: str
    name: str = ""
    source: str = "manual"
    relationship_type: str = "cold"   # warm | cold
    status: str = "active"
    tags: list[str] = Field(default_factory=list)


class ContactUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    source: Optional[str] = None
    relationship_type: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None


class EvidenceCreate(BaseModel):
    note: str


class CampaignCreate(BaseModel):
    name: str
    subject: str
    body: str
    sender_name: str = ""
    sender_email: str = ""
    sender_address: str = ""
    disclosures_text: str = ""


class RecipientAdd(BaseModel):
    contact_ids: list[str]
    actor: str = "system"


class ApproveRequest(BaseModel):
    approved_by: str


class DenyRequest(BaseModel):
    actor: str
    reason: str = ""


class SendRequest(BaseModel):
    actor: str = "system"


class SuppressionCreate(BaseModel):
    email: str
    reason: str = "opt_out"
    source: str = "manual"
    actor: str = "system"


class VerificationCreate(BaseModel):
    contact_id: str
    method: str = ""
    notes: str = ""
    actor: str = "system"


class VerificationUpdate(BaseModel):
    status: str
    verifier: str = ""
    documents_ref: str = ""
    notes: str = ""
    actor: str = "system"


class SaleRequest(BaseModel):
    contact_id: str
    amount: float = 0.0
    actor: str = "system"
    notes: str = ""


class FilingReminderCreate(BaseModel):
    filing_type: str
    due_date: str
    status: str = "pending"
    notes: str = ""


class HealthResponse(BaseModel):
    status: str
    module: str
    version: str
    db: str
