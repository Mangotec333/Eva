"""
EVA Retro-Agent — persistent memory (SQLite, stdlib only).

Append-only ledger of Weekly Retro Digests, modeled on
``modules/monetizing-agent/memory.py``: identity columns are frozen by an
immutability trigger (a digest is a historical fact — you never rewrite last
week's retro), and DELETEs are blocked outright. Each row stores the full digest
JSON so the API can replay any past week verbatim.

Tables:
  retro_runs      one row per retro pass (metadata + full digest JSON)
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.environ.get(
    "EVA_RETRO_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "retro_agent.db"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS retro_runs (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    week_start    TEXT NOT NULL DEFAULT '',
    week_end      TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT '',
    revenue_win   INTEGER NOT NULL DEFAULT 0,
    shipped_count         INTEGER NOT NULL DEFAULT 0,
    revenue_movement_count INTEGER NOT NULL DEFAULT 0,
    stale_blocker_count   INTEGER NOT NULL DEFAULT 0,
    priorities_addressed  INTEGER NOT NULL DEFAULT 0,
    priorities_total      INTEGER NOT NULL DEFAULT 0,
    narrative     TEXT NOT NULL DEFAULT '',
    digest_json   TEXT NOT NULL DEFAULT '{}'
);

-- Immutability: a persisted retro is a historical fact. Every column is frozen
-- once written; the row cannot be updated or deleted (append-only ledger).
CREATE TRIGGER IF NOT EXISTS retro_runs_no_update
BEFORE UPDATE ON retro_runs
BEGIN
    SELECT RAISE(ABORT, 'retro_runs is append-only: digests are immutable once written');
END;

CREATE TRIGGER IF NOT EXISTS retro_runs_no_delete
BEFORE DELETE ON retro_runs
BEGIN
    SELECT RAISE(ABORT, 'retro_runs is append-only: rows cannot be deleted');
END;
"""


def init_db(path: str = DB_PATH) -> None:
    """Create the table + triggers if absent (idempotent)."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def save_digest(digest: dict, *, path: str = DB_PATH) -> str:
    """Append a digest to the ledger. Returns the run id."""
    init_db(path)
    run_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO retro_runs
                (id, created_at, week_start, week_end, status, revenue_win,
                 shipped_count, revenue_movement_count, stale_blocker_count,
                 priorities_addressed, priorities_total, narrative, digest_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, _now(),
                digest.get("week_start", ""), digest.get("week_end", ""),
                digest.get("status", ""), 1 if digest.get("revenue_win") else 0,
                int(digest.get("shipped_count", 0)),
                int(digest.get("revenue_movement_count", 0)),
                len(digest.get("stale_blockers", []) or []),
                int(digest.get("priorities_addressed", 0)),
                int(digest.get("priorities_total", 0)),
                digest.get("narrative", ""),
                json.dumps(digest, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def _hydrate(row: sqlite3.Row) -> dict:
    rec = dict(row)
    try:
        rec["digest"] = json.loads(rec.get("digest_json") or "{}")
    except json.JSONDecodeError:
        rec["digest"] = {}
    return rec


def latest_digest(path: str = DB_PATH) -> Optional[dict]:
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM retro_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return _hydrate(row) if row else None
    finally:
        conn.close()


def list_digests(*, limit: int = 30, path: str = DB_PATH) -> list[dict]:
    init_db(path)
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM retro_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_hydrate(r) for r in rows]
    finally:
        conn.close()


def get_digest(run_id: str, path: str = DB_PATH) -> Optional[dict]:
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT * FROM retro_runs WHERE id = ?", (run_id,)).fetchone()
        return _hydrate(row) if row else None
    finally:
        conn.close()


__all__ = [
    "DB_PATH", "init_db", "save_digest", "latest_digest", "list_digests",
    "get_digest",
]
