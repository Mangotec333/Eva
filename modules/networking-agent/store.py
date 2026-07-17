"""
EVA Networking-Agent — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/outreach/database.py`` convention: standard-library
``sqlite3`` (no async deps) so the service runs fully offline, and an
append-only ``outcomes`` ledger made immutable with BEFORE UPDATE / BEFORE
DELETE triggers (same pattern as outreach's compliance ledger).

Tables
  * ``groups``   — Layer B community-scout entities (candidate → … → partner).
  * ``contacts`` — Layer A relationship-capital entities (unknown → … → partner).
  * ``drafts``   — draft → approved → sent/posted state machine for outbound
                   content against either entity type.
  * ``outcomes`` — append-only KAIZEN signal ledger (immutable via trigger).
  * ``kaizen_weights`` — the current per-signal outcome weights (upserted).

``init_db`` is idempotent (``CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS`` + a
default-weight seed guarded by INSERT OR IGNORE), so re-running it is a no-op.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_NETWORKING_DB",
    os.path.join(os.path.dirname(__file__), "eva-networking.db"),
)

# ---------------------------------------------------------------------------
# Domain vocab
# ---------------------------------------------------------------------------

# Layer B group lifecycle.
GROUP_STATUSES = [
    "candidate", "qualified", "engaged", "active", "partner", "rejected",
]
ACCESS_TYPES = ["public", "private", "paid", "invite_only"]

# Layer A relationship stage model.
CONTACT_STAGES = ["unknown", "engaged", "active", "partner"]

# Draft state machine.
DRAFT_STATUSES = ["draft", "approved", "sent", "rejected"]

# KAIZEN 10-signal outcome taxonomy (signal -> default weight in [-1, 1]).
# Positive signals reward the group/platform/tactic that produced them; negative
# signals penalise it. KAIZEN re-weights these from observed frequency.
OUTCOME_SIGNALS: dict[str, float] = {
    "joined": 0.10,
    "keyword_mention_found": 0.15,
    "content_engagement": 0.25,
    "reply_received": 0.40,
    "positive_reply": 0.70,
    "meeting_booked": 1.00,
    "intro_made": 0.85,
    "deal_referral": 0.90,
    "ignored": -0.20,
    "negative_reply": -0.50,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id                 TEXT PRIMARY KEY,
    platform           TEXT NOT NULL DEFAULT '',
    name               TEXT NOT NULL DEFAULT '',
    url                TEXT NOT NULL DEFAULT '',
    venture_tag        TEXT NOT NULL DEFAULT '',
    member_count       INTEGER NOT NULL DEFAULT 0,
    activity_score     REAL NOT NULL DEFAULT 0,
    topical_fit_score  REAL NOT NULL DEFAULT 0,
    access_type        TEXT NOT NULL DEFAULT 'public',
    status             TEXT NOT NULL DEFAULT 'candidate',
    discovered_via     TEXT NOT NULL DEFAULT '',
    score              REAL NOT NULL DEFAULT 0,
    notes              TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    handle        TEXT NOT NULL DEFAULT '',
    platform      TEXT NOT NULL DEFAULT '',
    venture_tag   TEXT NOT NULL DEFAULT '',
    stage         TEXT NOT NULL DEFAULT 'unknown',
    status        TEXT NOT NULL DEFAULT 'active',
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id            TEXT PRIMARY KEY,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    action        TEXT NOT NULL DEFAULT 'post',
    content       TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    approved_by   TEXT NOT NULL DEFAULT '',
    approved_at   TEXT NOT NULL DEFAULT '',
    sent_at       TEXT NOT NULL DEFAULT '',
    error         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    id            TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,
    entity_type   TEXT NOT NULL DEFAULT '',
    entity_id     TEXT NOT NULL DEFAULT '',
    action        TEXT NOT NULL DEFAULT '',
    outcome       TEXT NOT NULL DEFAULT '',
    signal        TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL DEFAULT '',
    details_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS kaizen_weights (
    signal        TEXT PRIMARY KEY,
    weight        REAL NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_groups_venture ON groups(venture_tag);
CREATE INDEX IF NOT EXISTS idx_groups_platform ON groups(platform);
CREATE INDEX IF NOT EXISTS idx_groups_status ON groups(status);
CREATE INDEX IF NOT EXISTS idx_contacts_stage ON contacts(stage);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_outcomes_entity ON outcomes(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_signal ON outcomes(signal);

-- The outcomes ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS outcomes_no_update
BEFORE UPDATE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS outcomes_no_delete
BEFORE DELETE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes ledger is append-only');
END;
"""


class Store:
    """Thin sync sqlite3 data-access layer. Opens a fresh connection per op."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            ts = _now()
            for signal, weight in OUTCOME_SIGNALS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO kaizen_weights (signal, weight, updated_at) "
                    "VALUES (?, ?, ?)",
                    (signal, weight, ts),
                )

    # -- groups -------------------------------------------------------------

    def insert_group(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": data.get("id") or str(uuid.uuid4()),
            "platform": data.get("platform", ""),
            "name": data.get("name", ""),
            "url": data.get("url", ""),
            "venture_tag": data.get("venture_tag", ""),
            "member_count": int(data.get("member_count", 0) or 0),
            "activity_score": float(data.get("activity_score", 0) or 0),
            "topical_fit_score": float(data.get("topical_fit_score", 0) or 0),
            "access_type": data.get("access_type", "public"),
            "status": data.get("status", "candidate"),
            "discovered_via": data.get("discovered_via", ""),
            "score": float(data.get("score", 0) or 0),
            "notes": data.get("notes", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO groups
                   (id, platform, name, url, venture_tag, member_count,
                    activity_score, topical_fit_score, access_type, status,
                    discovered_via, score, notes, created_at, updated_at)
                   VALUES (:id, :platform, :name, :url, :venture_tag,
                           :member_count, :activity_score, :topical_fit_score,
                           :access_type, :status, :discovered_via, :score,
                           :notes, :created_at, :updated_at)""",
                row,
            )
        return row

    def get_group(self, group_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM groups WHERE id = ?", (group_id,)
            ).fetchone()
        return dict(r) if r else None

    def get_group_by_url(self, url: str) -> Optional[dict]:
        if not url:
            return None
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM groups WHERE url = ? ORDER BY created_at LIMIT 1",
                (url,),
            ).fetchone()
        return dict(r) if r else None

    def list_groups(
        self, venture: Optional[str] = None, platform: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        clauses, params = [], []
        if venture:
            clauses.append("venture_tag = ?")
            params.append(venture)
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM groups {where} ORDER BY score DESC, created_at DESC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def update_group(self, group_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_group(group_id)
        cols = {k: v for k, v in fields.items() if v is not None}
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = group_id
        with self._connect() as conn:
            conn.execute(f"UPDATE groups SET {assignments} WHERE id = :id", cols)
        return self.get_group(group_id)

    # -- contacts (Layer A) -------------------------------------------------

    def insert_contact(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": data.get("id") or str(uuid.uuid4()),
            "name": data.get("name", ""),
            "handle": data.get("handle", ""),
            "platform": data.get("platform", ""),
            "venture_tag": data.get("venture_tag", ""),
            "stage": data.get("stage", "unknown"),
            "status": data.get("status", "active"),
            "notes": data.get("notes", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO contacts
                   (id, name, handle, platform, venture_tag, stage, status,
                    notes, created_at, updated_at)
                   VALUES (:id, :name, :handle, :platform, :venture_tag,
                           :stage, :status, :notes, :created_at, :updated_at)""",
                row,
            )
        return row

    def get_contact(self, contact_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_contacts(
        self, venture: Optional[str] = None, stage: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        clauses, params = [], []
        if venture:
            clauses.append("venture_tag = ?")
            params.append(venture)
        if stage:
            clauses.append("stage = ?")
            params.append(stage)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM contacts {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    def update_contact(self, contact_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_contact(contact_id)
        cols = {k: v for k, v in fields.items() if v is not None}
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = contact_id
        with self._connect() as conn:
            conn.execute(f"UPDATE contacts SET {assignments} WHERE id = :id", cols)
        return self.get_contact(contact_id)

    # -- drafts -------------------------------------------------------------

    def insert_draft(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "entity_type": data["entity_type"],
            "entity_id": data["entity_id"],
            "action": data.get("action", "post"),
            "content": data.get("content", ""),
            "status": "draft",
            "approved_by": "",
            "approved_at": "",
            "sent_at": "",
            "error": "",
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO drafts
                   (id, entity_type, entity_id, action, content, status,
                    approved_by, approved_at, sent_at, error, created_at, updated_at)
                   VALUES (:id, :entity_type, :entity_id, :action, :content,
                           :status, :approved_by, :approved_at, :sent_at, :error,
                           :created_at, :updated_at)""",
                row,
            )
        return row

    def get_draft(self, draft_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_drafts(
        self, status: Optional[str] = None, entity_id: Optional[str] = None
    ) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM drafts {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    def update_draft(self, draft_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_draft(draft_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = draft_id
        with self._connect() as conn:
            conn.execute(f"UPDATE drafts SET {assignments} WHERE id = :id", cols)
        return self.get_draft(draft_id)

    # -- outcomes ledger (append-only) --------------------------------------

    def append_outcome(
        self, entity_type: str, entity_id: str, outcome: str, signal: str = "",
        action: str = "", actor: str = "system", details: Optional[dict] = None,
    ) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "outcome": outcome,
            "signal": signal,
            "actor": actor,
            "details_json": json.dumps(details or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO outcomes
                   (id, ts, entity_type, entity_id, action, outcome, signal,
                    actor, details_json)
                   VALUES (:id, :ts, :entity_type, :entity_id, :action, :outcome,
                           :signal, :actor, :details_json)""",
                row,
            )
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def list_outcomes(
        self, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
        signal: Optional[str] = None,
    ) -> list[dict]:
        clauses, params = [], []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if signal:
            clauses.append("signal = ?")
            params.append(signal)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM outcomes {where} ORDER BY ts ASC", params
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

    # -- kaizen weights -----------------------------------------------------

    def get_weights(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT signal, weight FROM kaizen_weights"
            ).fetchall()
        return {r["signal"]: r["weight"] for r in rows}

    def set_weight(self, signal: str, weight: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kaizen_weights (signal, weight, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(signal) DO UPDATE SET weight = excluded.weight, "
                "updated_at = excluded.updated_at",
                (signal, weight, _now()),
            )


__all__ = [
    "Store", "DB_PATH",
    "GROUP_STATUSES", "ACCESS_TYPES", "CONTACT_STAGES", "DRAFT_STATUSES",
    "OUTCOME_SIGNALS",
]
