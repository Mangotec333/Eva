"""
EVA Meet Ingest — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/postcards`` / ``modules/outreach`` convention of using the
standard-library ``sqlite3`` module (no aiosqlite dependency) so the service is
fully runnable offline. The ``ledger`` table is made append-only with
BEFORE UPDATE / BEFORE DELETE triggers, exactly like postcards'
``publish_ledger``.

Tables (spec section 3):
  * ``meetings`` — one row per discovered recording.
  * ``memory``   — per-agent key/value memory (Agent Intelligence Layer).
  * ``ledger``   — append-only event trail (created/downloaded/transcribed/...).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_MEET_INGEST_DB",
    os.path.join(os.path.dirname(__file__), "meet_ingest.db"),
)

# Meeting lifecycle statuses.
MEETING_STATUSES = ["pending", "downloading", "transcribing", "done", "failed"]

# The single-row key under which the Drive poll watermark is stored in memory.
WATERMARK_KEY = "drive_poll_watermark"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id             TEXT PRIMARY KEY,
    drive_file_id  TEXT NOT NULL,
    name           TEXT NOT NULL DEFAULT '',
    recorded_at    TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'pending',
    transcript_path TEXT NOT NULL DEFAULT '',
    drive_upload_id TEXT NOT NULL DEFAULT '',
    error          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_recorded ON meetings(recorded_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_meetings_drive_file ON meetings(drive_file_id);

-- The ledger is append-only: block UPDATE and DELETE (mirrors postcards).
CREATE TRIGGER IF NOT EXISTS ledger_no_update
BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_no_delete
BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    # -- meetings -----------------------------------------------------------

    def insert_meeting(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "drive_file_id": data["drive_file_id"],
            "name": data.get("name", ""),
            "recorded_at": data.get("recorded_at", ""),
            "status": data.get("status", "pending"),
            "transcript_path": data.get("transcript_path", ""),
            "drive_upload_id": data.get("drive_upload_id", ""),
            "error": data.get("error", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO meetings
                   (id, drive_file_id, name, recorded_at, status, transcript_path,
                    drive_upload_id, error, created_at, updated_at)
                   VALUES (:id, :drive_file_id, :name, :recorded_at, :status,
                           :transcript_path, :drive_upload_id, :error,
                           :created_at, :updated_at)""",
                row,
            )
        return row

    def get_meeting(self, meeting_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
        return dict(r) if r else None

    def get_meeting_by_drive_file(self, drive_file_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM meetings WHERE drive_file_id = ? LIMIT 1",
                (drive_file_id,),
            ).fetchone()
        return dict(r) if r else None

    def list_meetings(self, status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM meetings {where} ORDER BY created_at", params
            ).fetchall()
        return [dict(r) for r in rows]

    def update_meeting(self, meeting_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_meeting(meeting_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = meeting_id
        with self._connect() as conn:
            conn.execute(f"UPDATE meetings SET {assignments} WHERE id = :id", cols)
        return self.get_meeting(meeting_id)

    # -- memory (Agent Intelligence Layer) ----------------------------------

    def get_memory(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return dict(r) if r else None

    def get_memory_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.get_memory(key)
        return row["value"] if row else default

    def set_memory(self, key: str, value: str, source: str = "system") -> dict:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source)
                   VALUES (:key, :value, :ts, :source)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value, ts = excluded.ts, source = excluded.source""",
                row,
            )
        return row

    def list_memory(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory ORDER BY key").fetchall()
        return [dict(r) for r in rows]

    # -- ledger -------------------------------------------------------------

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
                """INSERT INTO ledger
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
                f"SELECT * FROM ledger {where} ORDER BY ts ASC", params
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
