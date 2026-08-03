"""
EVA Deployer — SQLite persistence for the vercel_prod approval gate.

One table, ``deploys``, is the pending-approval queue + audit trail for every
``vercel_prod`` (live-site) deploy the CI/CD agent wants to ship. A remote-ahead
landing deploy is written as ``pending_approval`` and flipped to ``approved`` /
``denied`` / ``expired`` in place (and finally ``applied`` / ``failed`` once the
approved ``vercel --prod`` runs), so a launcher/CLI restart never loses an
in-flight approval.

Only the ``pull_and_restart`` (``eva``) action is left un-gated — restarting
Eva's own local services is low-stakes and already idle-gated. Shipping the live
marketing site is the irreversible action that earns a human gate.

Stdlib only. The DB lives beside this module and is gitignored (*.db).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "DEPLOYER_DB",
    os.path.join(os.path.dirname(__file__), "deployer.db"),
)

# Deploy lifecycle / audit statuses.
STATUS_PENDING_APPROVAL = "pending_approval"  # awaiting one-tap approval
STATUS_APPROVED = "approved"                  # approved → vercel will run
STATUS_DENIED = "denied"                      # explicitly denied → never shipped
STATUS_EXPIRED = "expired"                    # approval timed out → never shipped
STATUS_APPLIED = "applied"                    # approved + vercel --prod succeeded
STATUS_FAILED = "failed"                      # approved but vercel --prod failed

HISTORY_MAX = 200


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
            CREATE TABLE IF NOT EXISTS deploys (
                id               TEXT PRIMARY KEY,
                ts               TEXT NOT NULL,
                target           TEXT NOT NULL DEFAULT '',
                repo             TEXT NOT NULL DEFAULT '',
                path             TEXT NOT NULL DEFAULT '',
                old_sha          TEXT NOT NULL DEFAULT '',
                new_sha          TEXT NOT NULL DEFAULT '',
                changed_summary  TEXT NOT NULL DEFAULT '',
                status           TEXT NOT NULL DEFAULT 'pending_approval',
                triggered_by     TEXT NOT NULL DEFAULT 'eva',
                expires_at       TEXT NOT NULL DEFAULT '',
                updated_at       TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def create_deploy(*, target: str, repo: str, path: str, old_sha: str,
                  new_sha: str, changed_summary: str = "",
                  status: str = STATUS_PENDING_APPROVAL,
                  triggered_by: str = "eva", expires_at: str = "",
                  db_path: str | None = None) -> dict:
    """Insert one pending-deploy row and return it."""
    init_db(db_path)
    did = str(uuid.uuid4())
    now = _now()
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO deploys
               (id, ts, target, repo, path, old_sha, new_sha, changed_summary,
                status, triggered_by, expires_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (did, now, target, repo, path, old_sha, new_sha, changed_summary,
             status, triggered_by, expires_at, now),
        )
        conn.commit()
    return get_deploy(did, db_path=db_path)


def update_deploy(deploy_id: str, fields: dict,
                  db_path: str | None = None) -> dict | None:
    init_db(db_path)
    if not fields:
        return get_deploy(deploy_id, db_path=db_path)
    cols, vals = [], []
    for k, v in fields.items():
        cols.append(f"{k}=?")
        vals.append(v)
    cols.append("updated_at=?")
    vals.append(_now())
    vals.append(deploy_id)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE deploys SET {', '.join(cols)} WHERE id=?", vals)
        conn.commit()
    return get_deploy(deploy_id, db_path=db_path)


def get_deploy(deploy_id: str, db_path: str | None = None) -> dict | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM deploys WHERE id=?", (deploy_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_deploys(limit: int = 50, status: str | None = None,
                 db_path: str | None = None) -> list[dict]:
    """Recent deploys, newest first, capped."""
    init_db(db_path)
    limit = max(1, min(limit, HISTORY_MAX))
    with _connect(db_path) as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM deploys WHERE status=? ORDER BY ts DESC LIMIT ?",
                (status, limit))
        else:
            cur = conn.execute(
                "SELECT * FROM deploys ORDER BY ts DESC LIMIT ?", (limit,))
        return [_row_to_dict(r) for r in cur.fetchall()]


def count_by_status(db_path: str | None = None) -> dict:
    init_db(db_path)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "SELECT status, COUNT(*) c FROM deploys GROUP BY status")
        return {r["status"]: r["c"] for r in cur.fetchall()}


__all__ = [
    "DB_PATH", "HISTORY_MAX",
    "STATUS_PENDING_APPROVAL", "STATUS_APPROVED", "STATUS_DENIED",
    "STATUS_EXPIRED", "STATUS_APPLIED", "STATUS_FAILED",
    "init_db", "create_deploy", "update_deploy", "get_deploy", "list_deploys",
    "count_by_status",
]
