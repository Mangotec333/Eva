"""
EVA Deployer — SQLite persistence for the approve-then-deploy gate.

One table, ``deploy_requests``. A self-deploy (a live-Eva restart or a
``vercel --prod`` production ship) is an irreversible, state-changing action,
so — like the social-publish approve-then-publish gate — it is first recorded
as ``pending_approval`` and only executed once explicitly approved. State
survives launcher restarts so a ``POST /deployer/approve/{request_id}`` can
always resolve a request recorded on an earlier pass.

The DB lives beside this module and is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "DEPLOYER_DB",
    os.path.join(os.path.dirname(__file__), "deployer.db"),
)

# Deploy-request lifecycle (mirrors the social-publish / treasurer gates).
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_DEPLOYED = "deployed"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deploy_requests (
                id              TEXT PRIMARY KEY,
                target          TEXT NOT NULL,
                action          TEXT NOT NULL,
                local_sha       TEXT NOT NULL DEFAULT '',
                remote_sha      TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'pending_approval',
                approval_actor  TEXT NOT NULL DEFAULT '',
                approval_via    TEXT NOT NULL DEFAULT '',
                approved_at     TEXT NOT NULL DEFAULT '',
                result          TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def create_request(*, target: str, action: str, local_sha: str = "",
                   remote_sha: str = "", path: str | None = None) -> dict:
    """Record a deploy awaiting approval. Nothing is deployed yet."""
    init_db(path)
    rid = str(uuid.uuid4())
    now = _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO deploy_requests
               (id, target, action, local_sha, remote_sha, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rid, target, action, local_sha, remote_sha, STATUS_PENDING,
             now, now),
        )
        conn.commit()
    return get_request(rid, path=path)


def get_request(request_id: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM deploy_requests WHERE id=?", (request_id,)).fetchone()
        return _row_to_dict(row) if row else None


def find_open_request(*, target: str, remote_sha: str,
                      path: str | None = None) -> dict | None:
    """A still-open (pending/approved) request for this target+remote SHA.

    Lets a repeated poll pass reuse an outstanding request instead of stacking
    duplicates for the same commit (idempotent, like the spend/draft stores).
    """
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute(
            """SELECT * FROM deploy_requests
               WHERE target=? AND remote_sha=? AND status IN (?, ?)
               ORDER BY created_at DESC LIMIT 1""",
            (target, remote_sha, STATUS_PENDING, STATUS_APPROVED)).fetchone()
        return _row_to_dict(row) if row else None


def list_requests(status: str | None = None,
                  path: str | None = None) -> list[dict]:
    init_db(path)
    with _connect(path) as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM deploy_requests WHERE status=? ORDER BY created_at DESC",
                (status,))
        else:
            cur = conn.execute(
                "SELECT * FROM deploy_requests ORDER BY created_at DESC")
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_request(request_id: str, fields: dict,
                   path: str | None = None) -> dict | None:
    if not fields:
        return get_request(request_id, path=path)
    init_db(path)
    clean = dict(fields)
    clean["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in clean)
    params = list(clean.values()) + [request_id]
    with _connect(path) as conn:
        conn.execute(f"UPDATE deploy_requests SET {cols} WHERE id=?", params)
        conn.commit()
    return get_request(request_id, path=path)


__all__ = [
    "DB_PATH", "init_db",
    "STATUS_PENDING", "STATUS_APPROVED", "STATUS_DEPLOYED",
    "STATUS_FAILED", "STATUS_REJECTED",
    "create_request", "get_request", "find_open_request",
    "list_requests", "update_request",
]
