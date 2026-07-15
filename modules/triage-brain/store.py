"""
EVA Diracatron — SQLite persistence for the triage queue + dispatch history.

Two tables, both survive launcher/cron restarts:

  * ``triage_queue``     — one row per open item the brain is tracking. A
    stable ``signature`` (kind + entity + source) is UNIQUE so repeated triage
    passes are idempotent: re-seeing the same open item updates it in place
    instead of piling up duplicates (cron-safe, like the social-publish store).
  * ``dispatch_history`` — an append-only audit trail of every dispatch the
    brain made (which item, to which agent, the result), so decisions are
    replayable and the system can learn from what was tried.

The DB lives beside this module and is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "DIRACATRON_DB",
    os.path.join(os.path.dirname(__file__), "diracatron.db"),
)

# Item lifecycle.
STATUS_OPEN = "open"
STATUS_DISPATCHED = "dispatched"
STATUS_DONE = "done"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def signature(kind: str, entity_id: str, source: str) -> str:
    """Stable idempotency key for a triage item."""
    raw = f"{kind}|{entity_id}|{source}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()  # noqa: S324 - non-crypto dedup key


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_queue (
                id            TEXT PRIMARY KEY,
                signature     TEXT NOT NULL UNIQUE,
                kind          TEXT NOT NULL,
                source        TEXT NOT NULL DEFAULT '',
                entity_id     TEXT NOT NULL DEFAULT '',
                summary       TEXT NOT NULL DEFAULT '',
                priority      INTEGER NOT NULL DEFAULT 0,
                target_agent  TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'open',
                payload       TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dispatch_history (
                id            TEXT PRIMARY KEY,
                item_id       TEXT NOT NULL,
                signature     TEXT NOT NULL DEFAULT '',
                kind          TEXT NOT NULL DEFAULT '',
                target_agent  TEXT NOT NULL DEFAULT '',
                decided_by    TEXT NOT NULL DEFAULT 'diracatron',
                result        TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "payload" in d:
        d["payload"] = json.loads(d.get("payload") or "{}")
    if "result" in d:
        d["result"] = json.loads(d.get("result") or "{}")
    return d


# ---------------------------------------------------------------------------
# triage_queue
# ---------------------------------------------------------------------------

def upsert_item(*, kind: str, entity_id: str, source: str, summary: str,
                priority: int, target_agent: str, payload: dict | None = None,
                path: str | None = None) -> dict:
    """Insert a new open item, or refresh an existing open one in place.

    Idempotent on ``signature`` so a cron-driven triage pass never duplicates
    an item it has already seen. A DISPATCHED/DONE item is left untouched (we
    do not re-open something already handled in this cycle).
    """
    init_db(path)
    sig = signature(kind, entity_id, source)
    now = _now()
    payload_json = json.dumps(payload or {})
    with _connect(path) as conn:
        existing = conn.execute(
            "SELECT * FROM triage_queue WHERE signature=?", (sig,)
        ).fetchone()
        if existing is None:
            item_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO triage_queue
                   (id, signature, kind, source, entity_id, summary, priority,
                    target_agent, status, payload, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item_id, sig, kind, source, entity_id, summary, priority,
                 target_agent, STATUS_OPEN, payload_json, now, now),
            )
            conn.commit()
            return get_item(item_id, path=path)
        if existing["status"] == STATUS_OPEN:
            conn.execute(
                """UPDATE triage_queue
                   SET summary=?, priority=?, target_agent=?, payload=?, updated_at=?
                   WHERE id=?""",
                (summary, priority, target_agent, payload_json, now, existing["id"]),
            )
            conn.commit()
        return get_item(existing["id"], path=path)


def get_item(item_id: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM triage_queue WHERE id=?", (item_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_queue(status: str | None = STATUS_OPEN,
               path: str | None = None) -> list[dict]:
    """Ranked queue: highest priority first, then most-recent."""
    init_db(path)
    with _connect(path) as conn:
        if status:
            cur = conn.execute(
                """SELECT * FROM triage_queue WHERE status=?
                   ORDER BY priority DESC, updated_at DESC""",
                (status,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM triage_queue ORDER BY priority DESC, updated_at DESC"
            )
        return [_row_to_dict(r) for r in cur.fetchall()]


def set_status(item_id: str, status: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            "UPDATE triage_queue SET status=?, updated_at=? WHERE id=?",
            (status, _now(), item_id),
        )
        conn.commit()
    return get_item(item_id, path=path)


# ---------------------------------------------------------------------------
# dispatch_history
# ---------------------------------------------------------------------------

def record_dispatch(*, item_id: str, signature: str, kind: str,
                    target_agent: str, result: dict,
                    decided_by: str = "diracatron",
                    path: str | None = None) -> dict:
    init_db(path)
    did = str(uuid.uuid4())
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO dispatch_history
               (id, item_id, signature, kind, target_agent, decided_by, result, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (did, item_id, signature, kind, target_agent, decided_by,
             json.dumps(result), _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM dispatch_history WHERE id=?", (did,)
        ).fetchone()
        return _row_to_dict(row)


def list_dispatches(limit: int = 50, path: str | None = None) -> list[dict]:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute(
            "SELECT * FROM dispatch_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]
