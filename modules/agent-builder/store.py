"""
EVA Agent Builder — SQLite persistence for scaffolds and captured SOPs.

Two tables, both survive launcher restarts:

  * ``scaffolds``  — a row per module the builder scaffolds (audit trail of
    what was created, when, and which files were written).
  * ``sops``       — a row per captured one-off workflow, turned into a
    repeatable SOP (name, trigger, steps, the module it belongs to).

The DB lives beside this module and is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "AGENT_BUILDER_DB",
    os.path.join(os.path.dirname(__file__), "agent_builder.db"),
)


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
            CREATE TABLE IF NOT EXISTS scaffolds (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                slug         TEXT NOT NULL,
                port         INTEGER,
                purpose      TEXT DEFAULT '',
                files        TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sops (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                slug         TEXT NOT NULL,
                trigger      TEXT DEFAULT 'manual',
                summary      TEXT DEFAULT '',
                steps        TEXT NOT NULL DEFAULT '[]',
                inputs       TEXT NOT NULL DEFAULT '[]',
                module       TEXT DEFAULT '',
                sop_path     TEXT DEFAULT '',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row, json_fields: tuple[str, ...]) -> dict:
    d = dict(row)
    for f in json_fields:
        if f in d:
            d[f] = json.loads(d.get(f) or "[]")
    return d


# ---------------------------------------------------------------------------
# scaffolds
# ---------------------------------------------------------------------------

def record_scaffold(name: str, slug: str, port: int | None,
                    purpose: str, files: list[str]) -> dict:
    init_db()
    sid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO scaffolds (id, name, slug, port, purpose, files, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, name, slug, port, purpose, json.dumps(files), _now()),
        )
        conn.commit()
    return get_scaffold(sid)


def get_scaffold(sid: str) -> dict | None:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM scaffolds WHERE id=?", (sid,))
        row = cur.fetchone()
        return _row_to_dict(row, ("files",)) if row else None


def list_scaffolds() -> list[dict]:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM scaffolds ORDER BY created_at DESC")
        return [_row_to_dict(r, ("files",)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# sops (captured repeatable workflows)
# ---------------------------------------------------------------------------

def record_sop(name: str, slug: str, trigger: str, summary: str,
               steps: list[str], inputs: list[str],
               module: str = "", sop_path: str = "") -> dict:
    init_db()
    sid = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sops
               (id, name, slug, trigger, summary, steps, inputs, module, sop_path,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, name, slug, trigger, summary, json.dumps(steps),
             json.dumps(inputs), module, sop_path, now, now),
        )
        conn.commit()
    return get_sop(sid)


def get_sop(sid: str) -> dict | None:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM sops WHERE id=?", (sid,))
        row = cur.fetchone()
        return _row_to_dict(row, ("steps", "inputs")) if row else None


def list_sops() -> list[dict]:
    init_db()
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM sops ORDER BY created_at DESC")
        return [_row_to_dict(r, ("steps", "inputs")) for r in cur.fetchall()]
