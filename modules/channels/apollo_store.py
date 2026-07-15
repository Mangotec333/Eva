"""
EVA Channels — SQLite persistence for Apollo extraction batches.

Mirrors ``modules/social-publish/store.py``: one table, ``apollo_batches``,
that survives launcher restarts so ``POST /apollo/enroll/{batch_id}`` and the
Slack approval poller can always resolve a batch extracted earlier.

A batch holds the deduped, extracted contacts plus its approval/enrol status.
The DB lives beside this module and is gitignored (*.db).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "APOLLO_STORE_DB",
    os.path.join(os.path.dirname(__file__), "apollo_batches.db"),
)

# Batch lifecycle.
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_ENROLLED = "enrolled"
STATUS_PARTIAL = "partially_enrolled"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apollo_batches (
                id              TEXT PRIMARY KEY,
                query           TEXT DEFAULT '',
                source          TEXT DEFAULT 'apollo-pe-ma',
                contacts        TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'pending_approval',
                slack_channel   TEXT DEFAULT '',
                slack_ts        TEXT DEFAULT '',
                approval_actor  TEXT DEFAULT '',
                approval_via    TEXT DEFAULT '',
                approved_at     TEXT DEFAULT '',
                enroll_results  TEXT DEFAULT '{}',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["contacts"] = json.loads(d.get("contacts") or "[]")
    d["enroll_results"] = json.loads(d.get("enroll_results") or "{}")
    return d


def create_batch(contacts: list[dict], query: str = "",
                 source: str = "apollo-pe-ma") -> dict:
    init_db()
    batch_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO apollo_batches
               (id, query, source, contacts, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (batch_id, query, source, json.dumps(contacts),
             STATUS_PENDING, now, now),
        )
        conn.commit()
    return get_batch(batch_id)


def get_batch(batch_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM apollo_batches WHERE id=?", (batch_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def list_batches(status: str | None = None) -> list[dict]:
    init_db()
    with _connect() as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM apollo_batches WHERE status=? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cur = conn.execute("SELECT * FROM apollo_batches ORDER BY created_at DESC")
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_batch(batch_id: str, fields: dict) -> dict | None:
    if not fields:
        return get_batch(batch_id)
    init_db()
    clean = dict(fields)
    if "contacts" in clean and not isinstance(clean["contacts"], str):
        clean["contacts"] = json.dumps(clean["contacts"])
    if "enroll_results" in clean and not isinstance(clean["enroll_results"], str):
        clean["enroll_results"] = json.dumps(clean["enroll_results"])
    clean["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in clean)
    params = list(clean.values()) + [batch_id]
    with _connect() as conn:
        conn.execute(f"UPDATE apollo_batches SET {cols} WHERE id=?", params)
        conn.commit()
    return get_batch(batch_id)


__all__ = [
    "DB_PATH", "STATUS_PENDING", "STATUS_APPROVED", "STATUS_ENROLLED",
    "STATUS_PARTIAL", "STATUS_FAILED", "STATUS_REJECTED",
    "init_db", "create_batch", "get_batch", "list_batches", "update_batch",
    "_now",
]
