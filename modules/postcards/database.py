"""
EVA Postcards — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/outreach`` / ``deal-analyzer-agent`` convention of using
the standard-library ``sqlite3`` module (no aiosqlite dependency) so the service
is fully runnable offline. The ``publish_ledger`` table is made append-only with
BEFORE UPDATE / BEFORE DELETE triggers, exactly like outreach's
``compliance_ledger``.

Schema is as specified in the module spec, section 4.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from models import DEFAULT_CADENCE_DAYS, DEFAULT_START_DATE

DB_PATH = os.environ.get(
    "EVA_POSTCARDS_DB",
    os.path.join(os.path.dirname(__file__), "eva-postcards.db"),
)

# ---------------------------------------------------------------------------
# Schema (spec section 4) + indexes + append-only triggers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS postcards (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    theme         TEXT NOT NULL DEFAULT '',
    para1         TEXT NOT NULL DEFAULT '',
    para2         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    scheduled_at  TEXT NOT NULL DEFAULT '',
    posted_at     TEXT NOT NULL DEFAULT '',
    post_url      TEXT NOT NULL DEFAULT '',
    image_path    TEXT NOT NULL DEFAULT '',
    error         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS postcard_schedule (
    id     INTEGER PRIMARY KEY CHECK (id = 1),
    key    TEXT NOT NULL DEFAULT 'default',
    value  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS publish_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

-- Indexes (spec section 4)
CREATE INDEX IF NOT EXISTS idx_postcards_status ON postcards(status);
CREATE INDEX IF NOT EXISTS idx_postcards_scheduled ON postcards(scheduled_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_postcards_title ON postcards(title);

-- The publish ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS publish_ledger_no_update
BEFORE UPDATE ON publish_ledger
BEGIN
    SELECT RAISE(ABORT, 'publish_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS publish_ledger_no_delete
BEFORE DELETE ON publish_ledger
BEGIN
    SELECT RAISE(ABORT, 'publish_ledger is append-only');
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
        self._ensure_schedule_row()

    # -- postcards ----------------------------------------------------------

    def insert_card(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "title": data["title"],
            "theme": data.get("theme", ""),
            "para1": data.get("para1", ""),
            "para2": data.get("para2", ""),
            "status": data.get("status", "draft"),
            "scheduled_at": data.get("scheduled_at", ""),
            "posted_at": data.get("posted_at", ""),
            "post_url": data.get("post_url", ""),
            "image_path": data.get("image_path", ""),
            "error": data.get("error", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO postcards
                   (id, title, theme, para1, para2, status, scheduled_at,
                    posted_at, post_url, image_path, error, created_at, updated_at)
                   VALUES (:id, :title, :theme, :para1, :para2, :status,
                           :scheduled_at, :posted_at, :post_url, :image_path,
                           :error, :created_at, :updated_at)""",
                row,
            )
        return row

    def get_card(self, card_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM postcards WHERE id = ?", (card_id,)
            ).fetchone()
        return dict(r) if r else None

    def get_card_by_title(self, title: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM postcards WHERE title = ? LIMIT 1", (title,)
            ).fetchone()
        return dict(r) if r else None

    def list_cards(self, status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM postcards {where} ORDER BY created_at", params
            ).fetchall()
        return [dict(r) for r in rows]

    def next_due_card(self, now_iso: str) -> Optional[dict]:
        """The next approved card that is due.

        A card is due when it has an explicit ``scheduled_at <= now``, or when
        it has no explicit ``scheduled_at`` (in which case the schedule's own
        ``next_due`` clock, checked by the service, governs release). Ordered so
        explicitly-scheduled cards fire in scheduled order and unscheduled cards
        fire in creation order.
        """
        with self._connect() as conn:
            r = conn.execute(
                """SELECT * FROM postcards
                   WHERE status = 'approved'
                     AND (scheduled_at = '' OR scheduled_at <= ?)
                   ORDER BY
                     CASE WHEN scheduled_at = '' THEN created_at
                          ELSE scheduled_at END ASC
                   LIMIT 1""",
                (now_iso,),
            ).fetchone()
        return dict(r) if r else None

    def update_card(self, card_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_card(card_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = card_id
        with self._connect() as conn:
            conn.execute(f"UPDATE postcards SET {assignments} WHERE id = :id", cols)
        return self.get_card(card_id)

    # -- schedule (single-row config) --------------------------------------

    def _ensure_schedule_row(self) -> None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM postcard_schedule WHERE id = 1"
            ).fetchone()
            if r is None:
                default = {
                    "cadence_days": DEFAULT_CADENCE_DAYS,
                    "start_date": DEFAULT_START_DATE,
                    "next_due": DEFAULT_START_DATE,
                }
                conn.execute(
                    "INSERT INTO postcard_schedule (id, key, value) "
                    "VALUES (1, 'default', ?)",
                    (json.dumps(default),),
                )

    def get_schedule(self) -> dict:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM postcard_schedule WHERE id = 1"
            ).fetchone()
        return json.loads(r["value"]) if r else {}

    def update_schedule(self, fields: dict) -> dict:
        current = self.get_schedule()
        current.update({k: v for k, v in fields.items() if v is not None})
        with self._connect() as conn:
            conn.execute(
                "UPDATE postcard_schedule SET value = ? WHERE id = 1",
                (json.dumps(current),),
            )
        return current

    # -- publish ledger -----------------------------------------------------

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
                """INSERT INTO publish_ledger
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
                f"SELECT * FROM publish_ledger {where} ORDER BY ts ASC", params
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
