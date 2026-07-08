"""
EVA Outreach — service layer (compliance rules live here).

All enforced rules from spec section 7 are implemented in this one place so the
REST API and the CLI share identical behavior:

  * Approval-gated queue: recipients start ``pending_approval``; only an
    explicit human ``approve`` moves them to ``approved``; only ``approved``
    recipients can be sent. Nothing is ever auto-sent.
  * Global suppression is checked again at send time (a contact can opt out
    after being approved), so opting out blocks any future send.
  * A *send* (general solicitation / messaging) requires: approved AND not
    suppressed. Messaging a cold prospect is permitted under 506(c).
  * A *sale* is blocked for a cold contact unless a verification case is
    ``verified`` and unexpired. Warm contacts transact under 506(b).
  * Verification expires 365 days after ``verified_at``; a lapsed case is
    flipped to ``expired`` on read and the sale path re-locks.

Every mutating action appends to the append-only compliance ledger.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import Store
from models import (
    VERIFICATION_TRANSITIONS,
    VERIFICATION_TTL_DAYS,
)
from sender import OutboundMessage, Sender, build_sender


class ComplianceError(Exception):
    """Raised when a compliance rule blocks an action. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _disclosures_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class OutreachService:
    def __init__(self, store: Optional[Store] = None, sender: Optional[Sender] = None):
        self.store = store or Store()
        self.sender = sender or build_sender()

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def add_contact(self, payload: dict) -> dict:
        contact = self.store.insert_contact(payload)
        self.store.append_ledger(
            "contact_created",
            entity_type="contact",
            entity_id=contact["id"],
            actor=payload.get("actor", "system"),
            details={"email": contact["email"], "relationship_type": contact["relationship_type"]},
        )
        return contact

    def list_contacts(self, **filters) -> list[dict]:
        return self.store.list_contacts(**filters)

    def get_contact(self, contact_id: str) -> dict:
        contact = self.store.get_contact(contact_id)
        if not contact:
            raise NotFoundError(f"contact {contact_id!r} not found")
        return contact

    def update_contact(self, contact_id: str, fields: dict) -> dict:
        if not self.store.get_contact(contact_id):
            raise NotFoundError(f"contact {contact_id!r} not found")
        return self.store.update_contact(contact_id, fields)

    def add_relationship_evidence(self, contact_id: str, note: str) -> dict:
        if not self.store.get_contact(contact_id):
            raise NotFoundError(f"contact {contact_id!r} not found")
        ev = self.store.insert_evidence(contact_id, note)
        self.store.append_ledger(
            "relationship_evidence_added",
            entity_type="contact",
            entity_id=contact_id,
            details={"note": note},
        )
        return ev

    # ------------------------------------------------------------------
    # Campaigns + recipients
    # ------------------------------------------------------------------

    def create_campaign(self, payload: dict) -> dict:
        campaign = self.store.insert_campaign(payload)
        self.store.append_ledger(
            "campaign_created",
            entity_type="campaign",
            entity_id=campaign["id"],
            details={
                "name": campaign["name"],
                "disclosures_hash": _disclosures_hash(campaign["disclosures_text"]),
            },
        )
        return campaign

    def list_campaigns(self) -> list[dict]:
        return self.store.list_campaigns()

    def get_campaign(self, campaign_id: str) -> dict:
        campaign = self.store.get_campaign(campaign_id)
        if not campaign:
            raise NotFoundError(f"campaign {campaign_id!r} not found")
        return campaign

    def add_recipients(
        self, campaign_id: str, contact_ids: list[str], actor: str = "system"
    ) -> dict:
        """Add contacts to a campaign. Suppressed contacts are auto-excluded
        (recorded with status=suppressed + a ledger entry)."""
        self.get_campaign(campaign_id)
        added, excluded = [], []
        for contact_id in contact_ids:
            contact = self.store.get_contact(contact_id)
            if not contact:
                raise NotFoundError(f"contact {contact_id!r} not found")

            if self.store.get_suppression(contact["email"]):
                rec = self.store.insert_recipient(
                    campaign_id, contact_id, status="suppressed"
                )
                self.store.append_ledger(
                    "recipient_suppressed_excluded",
                    entity_type="campaign_recipient",
                    entity_id=rec["id"],
                    actor=actor,
                    details={
                        "campaign_id": campaign_id,
                        "contact_id": contact_id,
                        "email": contact["email"],
                    },
                )
                excluded.append(rec)
            else:
                rec = self.store.insert_recipient(campaign_id, contact_id)
                self.store.append_ledger(
                    "recipient_added",
                    entity_type="campaign_recipient",
                    entity_id=rec["id"],
                    actor=actor,
                    details={"campaign_id": campaign_id, "contact_id": contact_id},
                )
                added.append(rec)
        return {"added": added, "excluded": excluded}

    def list_recipients(self, campaign_id: str = None, status: str = None) -> list[dict]:
        return self.store.list_recipients(campaign_id=campaign_id, status=status)

    def list_pending(self) -> list[dict]:
        return self.store.list_recipients(status="pending_approval")

    def _get_recipient(self, recipient_id: str) -> dict:
        rec = self.store.get_recipient(recipient_id)
        if not rec:
            raise NotFoundError(f"recipient {recipient_id!r} not found")
        return rec

    def approve_recipient(self, recipient_id: str, approved_by: str) -> dict:
        rec = self._get_recipient(recipient_id)
        if rec["status"] not in ("pending_approval", "denied"):
            raise ComplianceError(
                "invalid_state",
                f"cannot approve recipient in status {rec['status']!r}",
            )
        if not approved_by:
            raise ComplianceError("approver_required", "approved_by is required")
        updated = self.store.update_recipient(
            recipient_id,
            {"status": "approved", "approved_by": approved_by, "approved_at": _now_iso()},
        )
        self.store.append_ledger(
            "recipient_approved",
            entity_type="campaign_recipient",
            entity_id=recipient_id,
            actor=approved_by,
            details={"campaign_id": rec["campaign_id"], "contact_id": rec["contact_id"]},
        )
        return updated

    def deny_recipient(self, recipient_id: str, actor: str, reason: str = "") -> dict:
        rec = self._get_recipient(recipient_id)
        updated = self.store.update_recipient(
            recipient_id, {"status": "denied", "error": reason}
        )
        self.store.append_ledger(
            "recipient_denied",
            entity_type="campaign_recipient",
            entity_id=recipient_id,
            actor=actor,
            details={"reason": reason, "campaign_id": rec["campaign_id"]},
        )
        return updated

    def send_recipient(self, recipient_id: str, actor: str = "system") -> dict:
        """Send an approved recipient. Blocks unless approved AND not suppressed."""
        rec = self._get_recipient(recipient_id)
        contact = self.store.get_contact(rec["contact_id"])
        campaign = self.store.get_campaign(rec["campaign_id"])

        # Gate 1: global suppression is paramount and re-checked at send time
        # (an opt-out may post-date approval, or even a prior send).
        if contact and self.store.get_suppression(contact["email"]):
            self.store.update_recipient(recipient_id, {"status": "suppressed"})
            self.store.append_ledger(
                "send_blocked",
                entity_type="campaign_recipient",
                entity_id=recipient_id,
                actor=actor,
                details={"reason": "suppressed", "email": contact["email"]},
            )
            raise ComplianceError(
                "suppressed", "contact is on the global suppression list"
            )

        # Gate 2: explicit human approval required.
        if rec["status"] != "approved":
            self.store.append_ledger(
                "send_blocked",
                entity_type="campaign_recipient",
                entity_id=recipient_id,
                actor=actor,
                details={"reason": "not_approved", "status": rec["status"]},
            )
            raise ComplianceError(
                "not_approved", "recipient must be approved before sending"
            )

        message = OutboundMessage(
            to_email=contact["email"],
            to_name=contact["name"],
            subject=campaign["subject"],
            body=campaign["body"],
            disclosures_text=campaign["disclosures_text"],
            sender_name=campaign["sender_name"],
            sender_email=campaign["sender_email"],
            sender_address=campaign["sender_address"],
            campaign_id=campaign["id"],
            recipient_id=recipient_id,
        )
        result = self.sender.send(message)

        if not result.ok:
            updated = self.store.update_recipient(
                recipient_id, {"status": "failed", "error": result.error}
            )
            self.store.append_ledger(
                "send_failed",
                entity_type="campaign_recipient",
                entity_id=recipient_id,
                actor=actor,
                details={"error": result.error, "provider": result.provider},
            )
            return updated

        sent_at = _now_iso()
        updated = self.store.update_recipient(
            recipient_id, {"status": "sent", "sent_at": sent_at, "error": ""}
        )
        self.store.append_ledger(
            "sent",
            entity_type="campaign_recipient",
            entity_id=recipient_id,
            actor=actor,
            details={
                "campaign_id": campaign["id"],
                "contact_id": contact["id"],
                "approved_by": rec["approved_by"],
                "sent_at": sent_at,
                "disclosures_hash": _disclosures_hash(campaign["disclosures_text"]),
                "provider": result.provider,
                "provider_message_id": result.provider_message_id,
            },
        )
        return updated

    # ------------------------------------------------------------------
    # Suppression / opt-out
    # ------------------------------------------------------------------

    def add_suppression(
        self, email: str, reason: str = "opt_out", source: str = "manual",
        actor: str = "system",
    ) -> dict:
        existing = self.store.get_suppression(email)
        if existing:
            # Global + immutable: already suppressed, return existing entry.
            return existing
        entry = self.store.insert_suppression(email, reason, source)
        self.store.append_ledger(
            "opt_out",
            entity_type="suppression",
            entity_id=entry["id"],
            actor=actor,
            details={"email": email, "reason": reason, "source": source},
        )
        return entry

    def check_suppression(self, email: str) -> dict:
        entry = self.store.get_suppression(email)
        return {"email": email, "suppressed": entry is not None, "entry": entry}

    def list_suppression(self) -> list[dict]:
        return self.store.list_suppression()

    # ------------------------------------------------------------------
    # Verification workflow
    # ------------------------------------------------------------------

    def create_verification(
        self, contact_id: str, method: str = "", notes: str = "", actor: str = "system"
    ) -> dict:
        if not self.store.get_contact(contact_id):
            raise NotFoundError(f"contact {contact_id!r} not found")
        case = self.store.insert_verification(
            {"contact_id": contact_id, "status": "requested", "method": method, "notes": notes}
        )
        self.store.append_ledger(
            "verification_created",
            entity_type="verification_case",
            entity_id=case["id"],
            actor=actor,
            details={"contact_id": contact_id, "method": method},
        )
        return case

    def list_verifications(self, contact_id: str = None, status: str = None) -> list[dict]:
        cases = self.store.list_verifications(contact_id=contact_id, status=status)
        return [self._refresh_expiry(c) for c in cases]

    def get_verification(self, case_id: str) -> dict:
        case = self.store.get_verification(case_id)
        if not case:
            raise NotFoundError(f"verification case {case_id!r} not found")
        return self._refresh_expiry(case)

    def advance_verification(
        self, case_id: str, status: str, verifier: str = "",
        documents_ref: str = "", notes: str = "", actor: str = "system",
    ) -> dict:
        case = self.store.get_verification(case_id)
        if not case:
            raise NotFoundError(f"verification case {case_id!r} not found")

        allowed_prior = VERIFICATION_TRANSITIONS.get(status)
        if allowed_prior is None:
            raise ComplianceError("invalid_status", f"unknown verification status {status!r}")
        if case["status"] not in allowed_prior:
            raise ComplianceError(
                "invalid_transition",
                f"cannot move verification from {case['status']!r} to {status!r}",
            )
        if status == "verified" and not verifier:
            raise ComplianceError("verifier_required", "verifier is required to verify")

        fields: dict = {"status": status}
        if verifier:
            fields["verifier"] = verifier
        if documents_ref:
            fields["documents_ref"] = documents_ref
        if notes:
            fields["notes"] = notes
        if status == "verified":
            verified_at = _now()
            fields["verified_at"] = verified_at.isoformat()
            fields["expires_at"] = (
                verified_at + timedelta(days=VERIFICATION_TTL_DAYS)
            ).isoformat()

        updated = self.store.update_verification(case_id, fields)
        self.store.append_ledger(
            "verification_advanced",
            entity_type="verification_case",
            entity_id=case_id,
            actor=actor,
            details={
                "from": case["status"],
                "to": status,
                "verifier": verifier,
                "expires_at": updated.get("expires_at", ""),
            },
        )
        return updated

    def _refresh_expiry(self, case: dict) -> dict:
        """If a verified case has passed its expiry, flip it to expired (persisted)."""
        if case["status"] == "verified" and case.get("expires_at"):
            try:
                expires = datetime.fromisoformat(case["expires_at"])
            except ValueError:
                return case
            if _now() > expires:
                updated = self.store.update_verification(case["id"], {"status": "expired"})
                self.store.append_ledger(
                    "verification_expired",
                    entity_type="verification_case",
                    entity_id=case["id"],
                    actor="system",
                    details={"contact_id": case["contact_id"], "expired_at": case["expires_at"]},
                )
                return updated
        return case

    def has_valid_verification(self, contact_id: str) -> bool:
        for case in self.list_verifications(contact_id=contact_id):
            if case["status"] == "verified":
                return True
        return False

    # ------------------------------------------------------------------
    # Sale path (506(c) gate)
    # ------------------------------------------------------------------

    def assert_sale_allowed(self, contact_id: str) -> None:
        contact = self.get_contact(contact_id)
        if contact["relationship_type"] == "warm":
            return  # 506(b): warm relationship, no accredited verification required
        if not self.has_valid_verification(contact_id):
            raise ComplianceError(
                "not_verified",
                "cold contact requires a verified, unexpired accredited-investor "
                "verification before a sale (SEC Rule 506(c))",
            )

    def record_sale(
        self, contact_id: str, amount: float = 0.0, actor: str = "system", notes: str = ""
    ) -> dict:
        self.assert_sale_allowed(contact_id)
        entry = self.store.append_ledger(
            "sale_recorded",
            entity_type="contact",
            entity_id=contact_id,
            actor=actor,
            details={"amount": amount, "notes": notes},
        )
        return entry

    # ------------------------------------------------------------------
    # Compliance ledger
    # ------------------------------------------------------------------

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    def export_ledger(self, fmt: str = "json") -> str:
        import csv
        import io
        import json

        rows = self.store.query_ledger()
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "ts", "event_type", "entity_type", "entity_id", "actor", "details_json"]
            )
            for r in rows:
                writer.writerow(
                    [r["id"], r["ts"], r["event_type"], r["entity_type"],
                     r["entity_id"], r["actor"], r.get("details_json", "{}")]
                )
            return buf.getvalue()
        return json.dumps(rows, indent=2)

    # ------------------------------------------------------------------
    # Filing reminders
    # ------------------------------------------------------------------

    def add_filing_reminder(self, payload: dict) -> dict:
        reminder = self.store.insert_filing_reminder(payload)
        self.store.append_ledger(
            "filing_reminder_created",
            entity_type="filing_reminder",
            entity_id=reminder["id"],
            details={"filing_type": reminder["filing_type"], "due_date": reminder["due_date"]},
        )
        return reminder

    def list_filing_reminders(self) -> list[dict]:
        return self.store.list_filing_reminders()
