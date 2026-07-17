"""
EVA Health Monitor — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/postcards`` / ``modules/outreach`` convention: standard
library ``sqlite3`` (no aiosqlite), fully offline-runnable. The ``ledger`` table
is append-only via BEFORE UPDATE / BEFORE DELETE triggers, exactly like
postcards' ``publish_ledger``. Per the Architecture Directive this module also
carries a ``memory`` table (per-agent long-term context).

Tables:
  * ``health_checks`` — one row per (module, tick): status, latency, code, error.
  * ``alerts``        — one row per raised alert (module down N ticks running).
  * ``memory``        — per-agent key/value memory (Agent Intelligence Layer).
  * ``ledger``        — append-only audit trail (checked/recovered/alert events).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_HEALTH_MONITOR_DB",
    os.path.join(os.path.dirname(__file__), "health_monitor.db"),
)

# Health check statuses.
STATUS_UP = "up"
STATUS_DOWN = "down"

# Alert statuses.
ALERT_OPEN = "open"
ALERT_RESOLVED = "resolved"

SCHEMA = """
CREATE TABLE IF NOT EXISTS health_checks (
    id            TEXT PRIMARY KEY,
    module        TEXT NOT NULL,
    url           TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'down',
    latency_ms    REAL NOT NULL DEFAULT -1,
    http_code     INTEGER NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    checked_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id                   TEXT PRIMARY KEY,
    module               TEXT NOT NULL,
    url                  TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'open',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    message              TEXT NOT NULL DEFAULT '',
    opened_at            TEXT NOT NULL,
    resolved_at          TEXT NOT NULL DEFAULT ''
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
CREATE INDEX IF NOT EXISTS idx_health_module ON health_checks(module);
CREATE INDEX IF NOT EXISTS idx_health_checked ON health_checks(checked_at);
CREATE INDEX IF NOT EXISTS idx_alerts_module ON alerts(module);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

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

    # -- health checks ------------------------------------------------------

    def insert_check(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "module": data["module"],
            "url": data.get("url", ""),
            "status": data.get("status", STATUS_DOWN),
            "latency_ms": data.get("latency_ms", -1),
            "http_code": data.get("http_code", 0),
            "error": data.get("error", ""),
            "checked_at": data.get("checked_at") or _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO health_checks
                   (id, module, url, status, latency_ms, http_code, error, checked_at)
                   VALUES (:id, :module, :url, :status, :latency_ms, :http_code,
                           :error, :checked_at)""",
                row,
            )
        return row

    def latest_checks(self) -> list[dict]:
        """The most recent check per module."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT h.* FROM health_checks h
                   JOIN (SELECT module, MAX(checked_at) AS m
                         FROM health_checks GROUP BY module) latest
                   ON h.module = latest.module AND h.checked_at = latest.m
                   ORDER BY h.module"""
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_checks(
        self, module: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        clauses, params = [], []
        if module:
            clauses.append("module = ?")
            params.append(module)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM health_checks {where} "
                f"ORDER BY checked_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def consecutive_failures(self, module: str) -> int:
        """Count trailing consecutive DOWN checks for a module (most recent
        first), stopping at the first UP. This is the alert trigger metric."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status FROM health_checks WHERE module = ? "
                "ORDER BY checked_at DESC",
                (module,),
            ).fetchall()
        count = 0
        for r in rows:
            if r["status"] == STATUS_DOWN:
                count += 1
            else:
                break
        return count

    # -- alerts -------------------------------------------------------------

    def open_alert_for(self, module: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM alerts WHERE module = ? AND status = ? "
                "ORDER BY opened_at DESC LIMIT 1",
                (module, ALERT_OPEN),
            ).fetchone()
        return dict(r) if r else None

    def insert_alert(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "module": data["module"],
            "url": data.get("url", ""),
            "status": data.get("status", ALERT_OPEN),
            "consecutive_failures": data.get("consecutive_failures", 0),
            "message": data.get("message", ""),
            "opened_at": data.get("opened_at") or _now(),
            "resolved_at": data.get("resolved_at", ""),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO alerts
                   (id, module, url, status, consecutive_failures, message,
                    opened_at, resolved_at)
                   VALUES (:id, :module, :url, :status, :consecutive_failures,
                           :message, :opened_at, :resolved_at)""",
                row,
            )
        return row

    def resolve_alert(self, alert_id: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.execute(
                "UPDATE alerts SET status = ?, resolved_at = ? WHERE id = ?",
                (ALERT_RESOLVED, _now(), alert_id),
            )
            r = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(r) if r else None

    def list_alerts(self, status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM alerts {where} ORDER BY opened_at DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    # -- memory (Agent Intelligence Layer) ----------------------------------

    def get_memory_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._connect() as conn:
            r = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else default

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
