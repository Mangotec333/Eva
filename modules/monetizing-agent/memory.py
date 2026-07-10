"""
EVA Monetizing Agent — persistent memory (SQLite, stdlib only)
==============================================================

Synchronous sqlite3 layer (stdlib — no aiosqlite) for the agent's long-term
memory. Modeled on ``deal-analyzer-agent/memory.py`` (the reference governed
module) and extended for the weekly revenue-leak scan.

Tables:

  memory                intelligence-layer key/value store (key, value, ts, source)
  agent_runs            one row per scan run (observe->score->act->learn loop)
  learnings             outcome feedback used to recalibrate scoring
  directive_versions    version history of the agent's live directive
  briefs                one row per weekly Sunday brief (state machine)
  monetization_plays    APPEND-ONLY ledger of packaged plays (immutability trigger)

The ``monetization_plays`` ledger is the audit trail for every packaged play.
Its identity columns are frozen by an immutability trigger; only the lifecycle
columns (status / executed_at / outcome) may transition, exactly as the doctrine
requires (pending-approval -> approved -> executed). DELETEs are blocked outright.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

# Play lifecycle states (also mirrored at the brief level).
STATUS_PENDING = "pending-approval"
STATUS_APPROVED = "approved"
STATUS_EXECUTED = "executed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id         TEXT PRIMARY KEY,
    brief_id   TEXT NOT NULL DEFAULT '',
    timestamp  TEXT NOT NULL,
    inputs     TEXT NOT NULL DEFAULT '{}',   -- mined signal summary
    outputs    TEXT NOT NULL DEFAULT '{}',   -- scored/ranked plays summary
    tokens     INTEGER NOT NULL DEFAULT 0,
    notes      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS learnings (
    id           TEXT PRIMARY KEY,
    play_id      TEXT NOT NULL DEFAULT '',
    play_type    TEXT NOT NULL DEFAULT '',
    outcome      TEXT NOT NULL DEFAULT '',      -- converted | no_response | declined | dead
    lesson       TEXT NOT NULL DEFAULT '',
    weight_delta TEXT NOT NULL DEFAULT '{}',    -- proposed {dimension: delta}
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS directive_versions (
    id         TEXT PRIMARY KEY,
    version    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefs (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    week_of       TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending-approval',
    est_cash      REAL NOT NULL DEFAULT 0,
    play_count    INTEGER NOT NULL DEFAULT 0,
    report_path   TEXT NOT NULL DEFAULT '',
    brief_text    TEXT NOT NULL DEFAULT '',
    feedback      TEXT NOT NULL DEFAULT ''       -- last-week feedback block
);

-- APPEND-ONLY ledger of packaged plays.
CREATE TABLE IF NOT EXISTS monetization_plays (
    play_id       TEXT PRIMARY KEY,
    brief_id      TEXT NOT NULL DEFAULT '',
    play_type     TEXT NOT NULL DEFAULT '',
    source_signal TEXT NOT NULL DEFAULT '',
    score         REAL NOT NULL DEFAULT 0,
    cash_estimate REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending-approval',
    action_artifact TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    executed_at   TEXT,
    outcome       TEXT NOT NULL DEFAULT ''
);

-- Immutability: identity/scoring columns are frozen once written; only the
-- lifecycle columns (status, executed_at, outcome) may change. DELETE is blocked.
CREATE TRIGGER IF NOT EXISTS plays_no_identity_update
BEFORE UPDATE ON monetization_plays
WHEN
    OLD.play_id       != NEW.play_id       OR
    OLD.brief_id      != NEW.brief_id      OR
    OLD.play_type     != NEW.play_type     OR
    OLD.source_signal != NEW.source_signal OR
    OLD.score         != NEW.score         OR
    OLD.cash_estimate != NEW.cash_estimate OR
    OLD.action_artifact != NEW.action_artifact OR
    OLD.created_at    != NEW.created_at
BEGIN
    SELECT RAISE(ABORT, 'monetization_plays is append-only: identity columns are immutable');
END;

CREATE TRIGGER IF NOT EXISTS plays_no_delete
BEFORE DELETE ON monetization_plays
BEGIN
    SELECT RAISE(ABORT, 'monetization_plays is append-only: rows cannot be deleted');
END;
"""


def init_db(path: str = DB_PATH) -> None:
    """Create all tables + triggers if absent (idempotent)."""
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


# ---------------------------------------------------------------------------
# memory (intelligence-layer key/value)
# ---------------------------------------------------------------------------

def remember(key: str, value: Any, source: str = "", path: str = DB_PATH) -> None:
    """Upsert a memory entry. ``value`` is JSON-encoded."""
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO memory (key, value, ts, source) VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value, ts=excluded.ts, source=excluded.source
            """,
            (key, json.dumps(value, default=str), _now(), source),
        )
        conn.commit()
    finally:
        conn.close()


def recall(key: str, default: Any = None, path: str = DB_PATH) -> Any:
    conn = _connect(path)
    try:
        row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# agent_runs
# ---------------------------------------------------------------------------

def save_run(brief_id: str, inputs: dict, outputs: dict, tokens: int = 0,
             notes: str = "", path: str = DB_PATH) -> str:
    run_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO agent_runs (id, brief_id, timestamp, inputs, outputs, tokens, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, brief_id, _now(), json.dumps(inputs, default=str),
             json.dumps(outputs, default=str), int(tokens), notes),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def latest_run(path: str = DB_PATH) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM agent_runs ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# learnings
# ---------------------------------------------------------------------------

def record_learning(play_id: str, play_type: str, outcome: str, lesson: str = "",
                    weight_delta: Optional[dict] = None, path: str = DB_PATH) -> str:
    learning_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO learnings (id, play_id, play_type, outcome, lesson, weight_delta, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (learning_id, play_id, play_type, outcome, lesson,
             json.dumps(weight_delta or {}, default=str), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return learning_id


def list_learnings(path: str = DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute("SELECT * FROM learnings ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# directive_versions
# ---------------------------------------------------------------------------

def save_directive_version(version: str, content: str, path: str = DB_PATH) -> str:
    row_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO directive_versions (id, version, content, updated_at) VALUES (?, ?, ?, ?)",
            (row_id, version, content, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return row_id


def get_latest_directive(path: str = DB_PATH) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM directive_versions ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# briefs
# ---------------------------------------------------------------------------

def save_brief(week_of: str, est_cash: float, play_count: int, report_path: str,
               brief_text: str, feedback: str = "", path: str = DB_PATH) -> str:
    brief_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO briefs (id, created_at, week_of, status, est_cash, play_count,
                                report_path, brief_text, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (brief_id, _now(), week_of, STATUS_PENDING, float(est_cash), int(play_count),
             report_path, brief_text, feedback),
        )
        conn.commit()
    finally:
        conn.close()
    return brief_id


def get_brief(brief_id: str, path: str = DB_PATH) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def latest_brief(path: str = DB_PATH) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM briefs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_brief_status(brief_id: str, status: str, path: str = DB_PATH) -> None:
    conn = _connect(path)
    try:
        conn.execute("UPDATE briefs SET status = ? WHERE id = ?", (status, brief_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# monetization_plays (append-only ledger)
# ---------------------------------------------------------------------------

def record_play(brief_id: str, play_type: str, source_signal: str, score: float,
                cash_estimate: float, action_artifact: dict,
                status: str = STATUS_PENDING, path: str = DB_PATH) -> str:
    """Append a packaged play to the ledger. Returns the play_id."""
    play_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO monetization_plays
                (play_id, brief_id, play_type, source_signal, score, cash_estimate,
                 status, action_artifact, created_at, executed_at, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '')
            """,
            (play_id, brief_id, play_type, source_signal, float(score),
             float(cash_estimate), status,
             json.dumps(action_artifact, default=str), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return play_id


def list_plays(brief_id: Optional[str] = None, path: str = DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        if brief_id:
            rows = conn.execute(
                "SELECT * FROM monetization_plays WHERE brief_id = ? ORDER BY score DESC",
                (brief_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM monetization_plays ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve_plays(brief_id: str, path: str = DB_PATH) -> int:
    """Flip every pending play of a brief to APPROVED (the approval gate).

    Returns the number of plays approved. Only the lifecycle ``status`` column
    changes, so the immutability trigger is satisfied.
    """
    conn = _connect(path)
    try:
        cur = conn.execute(
            "UPDATE monetization_plays SET status = ? WHERE brief_id = ? AND status = ?",
            (STATUS_APPROVED, brief_id, STATUS_PENDING),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def mark_executed(play_id: str, outcome: str = "", path: str = DB_PATH) -> None:
    """Mark an APPROVED play executed (records executed_at + outcome).

    Irreversible-action bookkeeping: a play must be APPROVED before it can be
    executed — enforced by the caller/service, recorded here.
    """
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE monetization_plays SET status = ?, executed_at = ?, outcome = ? "
            "WHERE play_id = ?",
            (STATUS_EXECUTED, _now(), outcome, play_id),
        )
        conn.commit()
    finally:
        conn.close()
