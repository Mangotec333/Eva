"""
EVA Projects — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/outreach`` / ``modules/postcards`` convention of using the
standard-library ``sqlite3`` module (no aiosqlite dependency) so the service is
fully runnable offline. The ``project_ledger`` table is made append-only with
BEFORE UPDATE / BEFORE DELETE triggers, exactly like outreach's
``compliance_ledger`` and postcards' ``publish_ledger``.

Nodes form a tree via ``parent_id`` (self-referential FK, ON DELETE CASCADE), so
deleting a node deletes its whole subtree.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

DB_PATH = os.environ.get(
    "EVA_PROJECTS_DB",
    os.path.join(os.path.dirname(__file__), "eva-projects.db"),
)

# ---------------------------------------------------------------------------
# Schema (spec section 4) + indexes + append-only triggers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS project_nodes (
    id          TEXT PRIMARY KEY,
    parent_id   TEXT REFERENCES project_nodes(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'none',
    status      TEXT NOT NULL DEFAULT '',
    meta        TEXT NOT NULL DEFAULT '',
    link        TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

-- Canonical per-agent memory (Architecture Directive). The append-only ledger
-- requirement is already satisfied by project_ledger above.
CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON project_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_sort ON project_nodes(parent_id, sort_order);

-- The project ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS project_ledger_no_update
BEFORE UPDATE ON project_ledger
BEGIN
    SELECT RAISE(ABORT, 'project_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS project_ledger_no_delete
BEFORE DELETE ON project_ledger
BEGIN
    SELECT RAISE(ABORT, 'project_ledger is append-only');
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

    # -- nodes --------------------------------------------------------------

    def insert_node(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": data.get("id") or str(uuid.uuid4()),
            "parent_id": data.get("parent_id"),
            "title": data["title"],
            "tier": data.get("tier", "none") or "none",
            "status": data.get("status", "") or "",
            "meta": data.get("meta", "") or "",
            "link": data.get("link", "") or "",
            "sort_order": data.get("sort_order", 0) or 0,
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO project_nodes
                   (id, parent_id, title, tier, status, meta, link, sort_order,
                    created_at, updated_at)
                   VALUES (:id, :parent_id, :title, :tier, :status, :meta, :link,
                           :sort_order, :created_at, :updated_at)""",
                row,
            )
        return row

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_nodes WHERE id = ?", (node_id,)
            ).fetchone()
        return dict(r) if r else None

    def get_root_by_title(self, title: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_nodes WHERE parent_id IS NULL AND title = ? "
                "LIMIT 1",
                (title,),
            ).fetchone()
        return dict(r) if r else None

    def list_nodes(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_nodes ORDER BY sort_order, created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def children_of(self, parent_id: Optional[str]) -> List[dict]:
        with self._connect() as conn:
            if parent_id is None:
                rows = conn.execute(
                    "SELECT * FROM project_nodes WHERE parent_id IS NULL "
                    "ORDER BY sort_order, created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM project_nodes WHERE parent_id = ? "
                    "ORDER BY sort_order, created_at",
                    (parent_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def max_sort_order(self, parent_id: Optional[str]) -> int:
        with self._connect() as conn:
            if parent_id is None:
                r = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_nodes "
                    "WHERE parent_id IS NULL"
                ).fetchone()
            else:
                r = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_nodes "
                    "WHERE parent_id = ?",
                    (parent_id,),
                ).fetchone()
        return int(r["m"])

    def update_node(self, node_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_node(node_id)
        cols = dict(fields)
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = node_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE project_nodes SET {assignments} WHERE id = :id", cols
            )
        return self.get_node(node_id)

    def delete_node(self, node_id: str) -> None:
        """Delete a node. ON DELETE CASCADE removes the whole subtree."""
        with self._connect() as conn:
            conn.execute("DELETE FROM project_nodes WHERE id = ?", (node_id,))

    def delete_all_nodes(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM project_nodes")

    def count_nodes(self) -> int:
        with self._connect() as conn:
            r = conn.execute("SELECT COUNT(*) AS c FROM project_nodes").fetchone()
        return int(r["c"])

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

    def list_memory(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory ORDER BY key").fetchall()
        return [dict(r) for r in rows]

    # -- ledger -------------------------------------------------------------

    def append_ledger(
        self,
        event_type: str,
        entity_id: str = "",
        actor: str = "",
        details: Optional[dict] = None,
    ) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "event_type": event_type,
            "entity_id": entity_id,
            "actor": actor,
            "details_json": json.dumps(details or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO project_ledger
                   (id, ts, event_type, entity_id, actor, details_json)
                   VALUES (:id, :ts, :event_type, :entity_id, :actor,
                           :details_json)""",
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
    ) -> List[dict]:
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
                f"SELECT * FROM project_ledger {where} ORDER BY ts ASC", params
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
