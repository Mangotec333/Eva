"""
EVA Outreach — SQLite persistence layer (stdlib sqlite3, sync).

Follows the deal-analyzer-agent convention of using the standard-library
``sqlite3`` module (no aiosqlite dependency) so the service is fully runnable
offline. The ``compliance_ledger`` and ``suppression_list`` tables are made
append-only / immutable with BEFORE UPDATE / BEFORE DELETE triggers.

Schema is exactly as specified in the module spec, section 4.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_OUTREACH_DB",
    os.path.join(os.path.dirname(__file__), "eva-outreach.db"),
)

# ---------------------------------------------------------------------------
# Schema (spec section 4) + indexes + append-only triggers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id                TEXT PRIMARY KEY,
    email             TEXT NOT NULL,
    name              TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL DEFAULT 'manual',
    relationship_type TEXT NOT NULL DEFAULT 'cold',
    status            TEXT NOT NULL DEFAULT 'active',
    tags_json         TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_relationship_evidence (
    id          TEXT PRIMARY KEY,
    contact_id  TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    subject          TEXT NOT NULL DEFAULT '',
    body             TEXT NOT NULL DEFAULT '',
    sender_name      TEXT NOT NULL DEFAULT '',
    sender_email     TEXT NOT NULL DEFAULT '',
    sender_address   TEXT NOT NULL DEFAULT '',
    disclosures_text TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_recipients (
    id           TEXT PRIMARY KEY,
    campaign_id  TEXT NOT NULL,
    contact_id   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending_approval',
    approved_by  TEXT NOT NULL DEFAULT '',
    approved_at  TEXT NOT NULL DEFAULT '',
    sent_at      TEXT NOT NULL DEFAULT '',
    error        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS suppression_list (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_cases (
    id             TEXT PRIMARY KEY,
    contact_id     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'requested',
    method         TEXT NOT NULL DEFAULT '',
    documents_ref  TEXT NOT NULL DEFAULT '',
    verifier       TEXT NOT NULL DEFAULT '',
    verified_at    TEXT NOT NULL DEFAULT '',
    expires_at     TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS compliance_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS filing_reminders (
    id           TEXT PRIMARY KEY,
    filing_type  TEXT NOT NULL,
    due_date     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    notes        TEXT NOT NULL DEFAULT ''
);

-- Canonical per-agent memory (Architecture Directive). The append-only ledger
-- requirement is already satisfied by compliance_ledger above.
CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

-- Indexes (spec section 4)
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_recipients_campaign_status
    ON campaign_recipients(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_suppression_email ON suppression_list(email);
CREATE INDEX IF NOT EXISTS idx_verifications_contact_status
    ON verification_cases(contact_id, status);

-- The compliance ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS ledger_no_update
BEFORE UPDATE ON compliance_ledger
BEGIN
    SELECT RAISE(ABORT, 'compliance_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_no_delete
BEFORE DELETE ON compliance_ledger
BEGIN
    SELECT RAISE(ABORT, 'compliance_ledger is append-only');
END;

-- Suppression is global and immutable (soft-delete semantics): no UPDATE/DELETE.
CREATE TRIGGER IF NOT EXISTS suppression_no_update
BEFORE UPDATE ON suppression_list
BEGIN
    SELECT RAISE(ABORT, 'suppression_list is immutable');
END;

CREATE TRIGGER IF NOT EXISTS suppression_no_delete
BEFORE DELETE ON suppression_list
BEGIN
    SELECT RAISE(ABORT, 'suppression_list is immutable');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Thin sync sqlite3 data-access layer. Opens a fresh connection per op."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    # -- connection helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- contacts -----------------------------------------------------------

    def insert_contact(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "email": data["email"],
            "name": data.get("name", ""),
            "source": data.get("source", "manual"),
            "relationship_type": data.get("relationship_type", "cold"),
            "status": data.get("status", "active"),
            "tags_json": json.dumps(data.get("tags", [])),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO contacts
                   (id, email, name, source, relationship_type, status,
                    tags_json, created_at, updated_at)
                   VALUES (:id, :email, :name, :source, :relationship_type,
                           :status, :tags_json, :created_at, :updated_at)""",
                row,
            )
        return self._contact_row(row)

    def get_contact(self, contact_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        return self._contact_row(dict(r)) if r else None

    def get_contact_by_email(self, email: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM contacts WHERE email = ? ORDER BY created_at LIMIT 1",
                (email,),
            ).fetchone()
        return self._contact_row(dict(r)) if r else None

    def list_contacts(
        self, relationship_type: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        clauses, params = [], []
        if relationship_type:
            clauses.append("relationship_type = ?")
            params.append(relationship_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM contacts {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._contact_row(dict(r)) for r in rows]

    def update_contact(self, contact_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_contact(contact_id)
        cols = {k: v for k, v in fields.items() if v is not None}
        if "tags" in cols:
            cols["tags_json"] = json.dumps(cols.pop("tags"))
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = contact_id
        with self._connect() as conn:
            conn.execute(f"UPDATE contacts SET {assignments} WHERE id = :id", cols)
        return self.get_contact(contact_id)

    @staticmethod
    def _contact_row(row: dict) -> dict:
        d = dict(row)
        raw = d.pop("tags_json", "[]")
        try:
            d["tags"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        return d

    # -- relationship evidence ---------------------------------------------

    def insert_evidence(self, contact_id: str, note: str) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "contact_id": contact_id,
            "note": note,
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO contact_relationship_evidence
                   (id, contact_id, note, created_at)
                   VALUES (:id, :contact_id, :note, :created_at)""",
                row,
            )
        return row

    def list_evidence(self, contact_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contact_relationship_evidence "
                "WHERE contact_id = ? ORDER BY created_at",
                (contact_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- campaigns ----------------------------------------------------------

    def insert_campaign(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "name": data["name"],
            "subject": data.get("subject", ""),
            "body": data.get("body", ""),
            "sender_name": data.get("sender_name", ""),
            "sender_email": data.get("sender_email", ""),
            "sender_address": data.get("sender_address", ""),
            "disclosures_text": data.get("disclosures_text", ""),
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO campaigns
                   (id, name, subject, body, sender_name, sender_email,
                    sender_address, disclosures_text, created_at)
                   VALUES (:id, :name, :subject, :body, :sender_name,
                           :sender_email, :sender_address, :disclosures_text,
                           :created_at)""",
                row,
            )
        return row

    def get_campaign(self, campaign_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_campaigns(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- campaign recipients ------------------------------------------------

    def insert_recipient(
        self, campaign_id: str, contact_id: str, status: str = "pending_approval"
    ) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "status": status,
            "approved_by": "",
            "approved_at": "",
            "sent_at": "",
            "error": "",
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO campaign_recipients
                   (id, campaign_id, contact_id, status, approved_by,
                    approved_at, sent_at, error, created_at)
                   VALUES (:id, :campaign_id, :contact_id, :status, :approved_by,
                           :approved_at, :sent_at, :error, :created_at)""",
                row,
            )
        return row

    def get_recipient(self, recipient_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM campaign_recipients WHERE id = ?", (recipient_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_recipients(
        self, campaign_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        clauses, params = [], []
        if campaign_id:
            clauses.append("campaign_id = ?")
            params.append(campaign_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM campaign_recipients {where} ORDER BY created_at",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def update_recipient(self, recipient_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_recipient(recipient_id)
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        params = dict(fields)
        params["id"] = recipient_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE campaign_recipients SET {assignments} WHERE id = :id",
                params,
            )
        return self.get_recipient(recipient_id)

    # -- suppression --------------------------------------------------------

    def insert_suppression(self, email: str, reason: str, source: str) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "email": email,
            "reason": reason,
            "source": source,
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO suppression_list (id, email, reason, source, created_at)
                   VALUES (:id, :email, :reason, :source, :created_at)""",
                row,
            )
        return row

    def get_suppression(self, email: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM suppression_list WHERE email = ? "
                "ORDER BY created_at LIMIT 1",
                (email,),
            ).fetchone()
        return dict(r) if r else None

    def list_suppression(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM suppression_list ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- verifications ------------------------------------------------------

    def insert_verification(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "contact_id": data["contact_id"],
            "status": data.get("status", "requested"),
            "method": data.get("method", ""),
            "documents_ref": data.get("documents_ref", ""),
            "verifier": data.get("verifier", ""),
            "verified_at": data.get("verified_at", ""),
            "expires_at": data.get("expires_at", ""),
            "notes": data.get("notes", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO verification_cases
                   (id, contact_id, status, method, documents_ref, verifier,
                    verified_at, expires_at, notes, created_at, updated_at)
                   VALUES (:id, :contact_id, :status, :method, :documents_ref,
                           :verifier, :verified_at, :expires_at, :notes,
                           :created_at, :updated_at)""",
                row,
            )
        return row

    def get_verification(self, case_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM verification_cases WHERE id = ?", (case_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_verifications(
        self, contact_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        clauses, params = [], []
        if contact_id:
            clauses.append("contact_id = ?")
            params.append(contact_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM verification_cases {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def update_verification(self, case_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_verification(case_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = case_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE verification_cases SET {assignments} WHERE id = :id", cols
            )
        return self.get_verification(case_id)

    # -- compliance ledger --------------------------------------------------

    def append_ledger(
        self,
        event_type: str,
        entity_type: str = "",
        entity_id: str = "",
        actor: str = "",
        details: Optional[dict] = None,
    ) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor": actor,
            "details_json": json.dumps(details or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO compliance_ledger
                   (id, ts, event_type, entity_type, entity_id, actor, details_json)
                   VALUES (:id, :ts, :event_type, :entity_type, :entity_id,
                           :actor, :details_json)""",
                row,
            )
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def query_ledger(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        clauses, params = [], []
        if from_ts:
            clauses.append("ts >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("ts <= ?")
            params.append(to_ts)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM compliance_ledger {where} ORDER BY ts ASC", params
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
            out.append(d)
        return out

    # -- memory (per-agent knowledge) --------------------------------------

    def set_memory(self, key: str, value: str, source: str = "system") -> dict:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                     value=excluded.value, ts=excluded.ts, source=excluded.source""",
                (key, value, now, source),
            )
        return {"key": key, "value": value, "ts": now, "source": source}

    def get_memory(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return r["value"] if r else default

    def list_memory(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory ORDER BY key").fetchall()
        return [dict(r) for r in rows]

    # -- filing reminders ---------------------------------------------------

    def insert_filing_reminder(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "filing_type": data["filing_type"],
            "due_date": data.get("due_date", ""),
            "status": data.get("status", "pending"),
            "notes": data.get("notes", ""),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO filing_reminders
                   (id, filing_type, due_date, status, notes)
                   VALUES (:id, :filing_type, :due_date, :status, :notes)""",
                row,
            )
        return row

    def list_filing_reminders(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM filing_reminders ORDER BY due_date"
            ).fetchall()
        return [dict(r) for r in rows]
