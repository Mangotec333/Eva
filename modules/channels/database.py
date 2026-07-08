"""
EVA Channels — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/postcards`` / ``modules/projects`` convention of using the
standard-library ``sqlite3`` module (no aiosqlite dependency) so the service is
fully runnable offline. The ``channels_ledger`` table is made append-only with
BEFORE UPDATE / BEFORE DELETE triggers, exactly like outreach's
``compliance_ledger`` and postcards' ``publish_ledger``.

Schema is as specified in the module spec, section 4. A ``memory`` table backs
the agent intelligence layer (read on task start, written on decision/learning).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from models import DEFAULT_CADENCE_DAYS, DEFAULT_PLATFORM_CONFIG

DB_PATH = os.environ.get(
    "EVA_CHANNELS_DB",
    os.path.join(os.path.dirname(__file__), "eva-channels.db"),
)

# ---------------------------------------------------------------------------
# Schema (spec section 4) + indexes + append-only triggers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_items (
    id            TEXT PRIMARY KEY,
    platform      TEXT NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    payload_json  TEXT NOT NULL DEFAULT '{}',
    scheduled_at  TEXT NOT NULL DEFAULT '',
    posted_at     TEXT NOT NULL DEFAULT '',
    post_url      TEXT NOT NULL DEFAULT '',
    error         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_platform_config (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    key    TEXT NOT NULL UNIQUE,
    value  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS channel_schedule (
    id     INTEGER PRIMARY KEY CHECK (id = 1),
    key    TEXT NOT NULL DEFAULT 'default',
    value  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS channels_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

-- Indexes (spec section 4)
CREATE INDEX IF NOT EXISTS idx_items_status ON channel_items(status);
CREATE INDEX IF NOT EXISTS idx_items_platform ON channel_items(platform);
CREATE INDEX IF NOT EXISTS idx_items_scheduled ON channel_items(scheduled_at);

-- The channels ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS channels_ledger_no_update
BEFORE UPDATE ON channels_ledger
BEGIN
    SELECT RAISE(ABORT, 'channels_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS channels_ledger_no_delete
BEFORE DELETE ON channels_ledger
BEGIN
    SELECT RAISE(ABORT, 'channels_ledger is append-only');
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
        self._ensure_platform_configs()

    # -- items --------------------------------------------------------------

    def insert_item(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "platform": data["platform"],
            "title": data["title"],
            "body": data.get("body", ""),
            "status": data.get("status", "draft"),
            "payload_json": data.get("payload_json") or "{}",
            "scheduled_at": data.get("scheduled_at", ""),
            "posted_at": data.get("posted_at", ""),
            "post_url": data.get("post_url", ""),
            "error": data.get("error", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO channel_items
                   (id, platform, title, body, status, payload_json, scheduled_at,
                    posted_at, post_url, error, created_at, updated_at)
                   VALUES (:id, :platform, :title, :body, :status, :payload_json,
                           :scheduled_at, :posted_at, :post_url, :error,
                           :created_at, :updated_at)""",
                row,
            )
        return row

    def get_item(self, item_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM channel_items WHERE id = ?", (item_id,)
            ).fetchone()
        return dict(r) if r else None

    def list_items(self, status: Optional[str] = None,
                   platform: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM channel_items {where} ORDER BY created_at", params
            ).fetchall()
        return [dict(r) for r in rows]

    def next_due_item(self, now_iso: str) -> Optional[dict]:
        """The next approved item that is due (explicit scheduled_at in the
        past, or no explicit schedule). Explicitly-scheduled items fire in
        scheduled order; unscheduled items fire in creation order."""
        with self._connect() as conn:
            r = conn.execute(
                """SELECT * FROM channel_items
                   WHERE status = 'approved'
                     AND (scheduled_at = '' OR scheduled_at <= ?)
                   ORDER BY
                     CASE WHEN scheduled_at = '' THEN created_at
                          ELSE scheduled_at END ASC
                   LIMIT 1""",
                (now_iso,),
            ).fetchone()
        return dict(r) if r else None

    def count_by_status(self, status: str) -> int:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM channel_items WHERE status = ?",
                (status,),
            ).fetchone()
        return int(r["c"])

    def update_item(self, item_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_item(item_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = item_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE channel_items SET {assignments} WHERE id = :id", cols
            )
        return self.get_item(item_id)

    # -- platform config ----------------------------------------------------

    def _ensure_platform_configs(self) -> None:
        with self._connect() as conn:
            for platform, default in DEFAULT_PLATFORM_CONFIG.items():
                r = conn.execute(
                    "SELECT 1 FROM channel_platform_config WHERE key = ?",
                    (platform,),
                ).fetchone()
                if r is None:
                    conn.execute(
                        "INSERT INTO channel_platform_config (key, value) "
                        "VALUES (?, ?)",
                        (platform, json.dumps(default)),
                    )

    def get_config(self, platform: str) -> dict:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM channel_platform_config WHERE key = ?",
                (platform,),
            ).fetchone()
        if r is None:
            return dict(DEFAULT_PLATFORM_CONFIG.get(platform, {}))
        return json.loads(r["value"])

    def update_config(self, platform: str, values: dict) -> dict:
        current = self.get_config(platform)
        current.update({k: v for k, v in values.items() if v is not None})
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO channel_platform_config (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (platform, json.dumps(current)),
            )
        return current

    # -- schedule (single-row config) --------------------------------------

    def _ensure_schedule_row(self) -> None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM channel_schedule WHERE id = 1"
            ).fetchone()
            if r is None:
                default = {"cadence_days": DEFAULT_CADENCE_DAYS, "next_due": ""}
                conn.execute(
                    "INSERT INTO channel_schedule (id, key, value) "
                    "VALUES (1, 'default', ?)",
                    (json.dumps(default),),
                )

    def get_schedule(self) -> dict:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM channel_schedule WHERE id = 1"
            ).fetchone()
        return json.loads(r["value"]) if r else {}

    def update_schedule(self, fields: dict) -> dict:
        current = self.get_schedule()
        current.update({k: v for k, v in fields.items() if v is not None})
        with self._connect() as conn:
            conn.execute(
                "UPDATE channel_schedule SET value = ? WHERE id = 1",
                (json.dumps(current),),
            )
        return current

    # -- memory (agent intelligence layer) ----------------------------------

    def set_memory(self, key: str, value: str, source: str = "") -> dict:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory (key, value, ts, source) "
                "VALUES (:key, :value, :ts, :source) "
                "ON CONFLICT(key) DO UPDATE SET "
                "value = excluded.value, ts = excluded.ts, source = excluded.source",
                row,
            )
        return row

    def get_memory(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return dict(r) if r else None

    def all_memory(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory ORDER BY ts DESC"
            ).fetchall()
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
                """INSERT INTO channels_ledger
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
                f"SELECT * FROM channels_ledger {where} ORDER BY ts ASC", params
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
