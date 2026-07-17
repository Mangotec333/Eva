"""
EVA Social-Publish — SQLite persistence for the approve-then-publish gate.

One table, ``social_drafts``. State survives launcher restarts so the
``POST /social/approve/{draft_id}`` fallback endpoint can always resolve a
draft submitted earlier. The DB lives beside this module and is gitignored
(*.db).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "SOCIAL_PUBLISH_DB",
    os.path.join(os.path.dirname(__file__), "social_publish.db"),
)

# Draft lifecycle.
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_PUBLISHED = "published"
STATUS_PARTIAL = "partially_published"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Canonical per-agent memory + append-only ledger (Architecture Directive).
# Schema + immutability triggers copied verbatim from the reference modules
# (modules/postcards, modules/meet-ingest).
# ---------------------------------------------------------------------------

_MEM_LEDGER_SCHEMA = """
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


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS social_drafts (
                id              TEXT PRIMARY KEY,
                text            TEXT NOT NULL,
                image_path      TEXT DEFAULT '',
                platforms       TEXT NOT NULL DEFAULT '["linkedin","x"]',
                status          TEXT NOT NULL DEFAULT 'pending_approval',
                slack_channel   TEXT DEFAULT '',
                slack_ts        TEXT DEFAULT '',
                approval_actor  TEXT DEFAULT '',
                approval_via    TEXT DEFAULT '',
                approved_at     TEXT DEFAULT '',
                publish_results TEXT DEFAULT '{}',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )
        conn.executescript(_MEM_LEDGER_SCHEMA)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["platforms"] = json.loads(d.get("platforms") or "[]")
    d["publish_results"] = json.loads(d.get("publish_results") or "{}")
    return d


def create_draft(text: str, image_path: str = "",
                 platforms: list[str] | None = None) -> dict:
    init_db()
    draft_id = str(uuid.uuid4())
    now = _now()
    platforms = platforms or ["linkedin", "x"]
    with _connect() as conn:
        conn.execute(
            """INSERT INTO social_drafts
               (id, text, image_path, platforms, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (draft_id, text, image_path or "", json.dumps(platforms),
             STATUS_PENDING, now, now),
        )
        conn.commit()
    return get_draft(draft_id)


def get_draft(draft_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM social_drafts WHERE id=?", (draft_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def list_drafts(status: str | None = None) -> list[dict]:
    init_db()
    with _connect() as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM social_drafts WHERE status=? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cur = conn.execute("SELECT * FROM social_drafts ORDER BY created_at DESC")
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_draft(draft_id: str, fields: dict) -> dict | None:
    if not fields:
        return get_draft(draft_id)
    init_db()
    clean = dict(fields)
    if "platforms" in clean and not isinstance(clean["platforms"], str):
        clean["platforms"] = json.dumps(clean["platforms"])
    if "publish_results" in clean and not isinstance(clean["publish_results"], str):
        clean["publish_results"] = json.dumps(clean["publish_results"])
    clean["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in clean)
    params = list(clean.values()) + [draft_id]
    with _connect() as conn:
        conn.execute(f"UPDATE social_drafts SET {cols} WHERE id=?", params)
        conn.commit()
    return get_draft(draft_id)


# ---------------------------------------------------------------------------
# memory (per-agent knowledge) + append-only ledger accessors
# ---------------------------------------------------------------------------

def set_memory(key: str, value: str, source: str = "system") -> dict:
    init_db()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, ts=excluded.ts, source=excluded.source""",
            (key, value, now, source),
        )
        conn.commit()
    return {"key": key, "value": value, "ts": now, "source": source}


def get_memory(key: str, default: str | None = None) -> str | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def list_memory() -> list[dict]:
    init_db()
    with _connect() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM memory ORDER BY key").fetchall()]


def append_ledger(event_type: str, entity_type: str = "", entity_id: str = "",
                  actor: str = "", details: dict | None = None) -> dict:
    init_db()
    row = {
        "id": str(uuid.uuid4()), "ts": _now(), "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id, "actor": actor,
        "details_json": json.dumps(details or {}),
    }
    with _connect() as conn:
        conn.execute(
            """INSERT INTO ledger
               (id, ts, event_type, entity_type, entity_id, actor, details_json)
               VALUES (:id,:ts,:event_type,:entity_type,:entity_id,:actor,:details_json)""",
            row,
        )
        conn.commit()
    out = dict(row)
    out["details"] = json.loads(out.pop("details_json"))
    return out


def query_ledger(event_type: str | None = None) -> list[dict]:
    init_db()
    q, params = "SELECT * FROM ledger", []
    if event_type:
        q += " WHERE event_type=?"
        params.append(event_type)
    q += " ORDER BY ts ASC"
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
    return rows
