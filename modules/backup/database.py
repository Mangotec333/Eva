"""
EVA Backup — SQLite persistence (stdlib sqlite3, sync).

Two tables, both canonical EVA conventions:

  memory         intelligence-layer key/value store (key, value, ts, source) —
                 the module's own long-term memory (last run, last archive id…),
                 modeled on ``modules/monetizing-agent/memory.py``.
  backup_ledger  APPEND-ONLY audit trail of every backup attempt (success or
                 failure) + retention deletes, made immutable with BEFORE
                 UPDATE / BEFORE DELETE triggers exactly like
                 ``modules/postcards`` ``publish_ledger``.

Fresh connection per op; no shared runtime state.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_BACKUP_DB",
    os.path.join(os.path.dirname(__file__), "eva-backup.db"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS backup_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,               -- backup_ok | backup_error | retention_delete
    entity_type  TEXT NOT NULL DEFAULT '',    -- archive | file
    entity_id    TEXT NOT NULL DEFAULT '',    -- Drive file id (when known)
    actor        TEXT NOT NULL DEFAULT '',    -- tick | cli | http
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_backup_ledger_ts ON backup_ledger(ts);
CREATE INDEX IF NOT EXISTS idx_backup_ledger_event ON backup_ledger(event_type);

-- The backup ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS backup_ledger_no_update
BEFORE UPDATE ON backup_ledger
BEGIN
    SELECT RAISE(ABORT, 'backup_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS backup_ledger_no_delete
BEFORE DELETE ON backup_ledger
BEGIN
    SELECT RAISE(ABORT, 'backup_ledger is append-only');
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

    # -- memory (key/value intelligence layer) ------------------------------

    def remember(self, key: str, value: str, source: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       ts = excluded.ts,
                       source = excluded.source""",
                (key, value, _now(), source),
            )

    def recall(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return r["value"] if r else None

    def all_memory(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, ts, source FROM memory ORDER BY key"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- backup ledger (append-only) ----------------------------------------

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
                """INSERT INTO backup_ledger
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
        limit: Optional[int] = None,
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
        sql = f"SELECT * FROM backup_ledger {where} ORDER BY ts DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
            out.append(d)
        return out
