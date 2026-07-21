"""
EVA Channels — SQLite persistence for Storeys investor-sourcing batches.

Mirrors ``apollo_store.py`` exactly but is a **separate table/DB** so Storeys
investor-outreach batches never mix with Eva Acquisition (PE/M&A) batches.
Per standing instruction, new Storeys plumbing must not touch the Eva
Acquisition pipeline/tables — this file (and its sibling gate/ledger) is the
Storeys-only copy of that pattern.

A batch holds the deduped, extracted investor contacts plus its
approval/enrol status. The DB lives beside this module and is gitignored
(*.db).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "STOREYS_INVESTOR_STORE_DB",
    os.path.join(os.path.dirname(__file__), "storeys_investor_batches.db"),
)

# Batch lifecycle (same states as apollo_store.py).
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
            CREATE TABLE IF NOT EXISTS storeys_investor_batches (
                id              TEXT PRIMARY KEY,
                query           TEXT DEFAULT '',
                source          TEXT DEFAULT 'apollo-re-investor',
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
                 source: str = "apollo-re-investor") -> dict:
    init_db()
    batch_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO storeys_investor_batches
                (id, query, source, contacts, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, query, source, json.dumps(contacts),
             STATUS_PENDING, now, now),
        )
        conn.commit()
    return get_batch(batch_id)


def get_batch(batch_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM storeys_investor_batches WHERE id = ?", (batch_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_batches(status: str | None = None) -> list[dict]:
    init_db()
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM storeys_investor_batches WHERE status = ? "
                "ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM storeys_investor_batches ORDER BY created_at DESC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_batch(batch_id: str, fields: dict) -> dict | None:
    init_db()
    payload = dict(fields)
    for key in ("contacts", "enroll_results"):
        if key in payload and not isinstance(payload[key], str):
            payload[key] = json.dumps(payload[key])
    payload["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in payload)
    values = list(payload.values()) + [batch_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE storeys_investor_batches SET {cols} WHERE id = ?", values
        )
        conn.commit()
    return get_batch(batch_id)


__all__ = [
    "DB_PATH", "STATUS_PENDING", "STATUS_APPROVED", "STATUS_ENROLLED",
    "STATUS_PARTIAL", "STATUS_FAILED", "STATUS_REJECTED",
    "init_db", "create_batch", "get_batch", "list_batches", "update_batch",
]
