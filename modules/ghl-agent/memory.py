"""
EVA GHL Agent — persistent memory (SQLite, stdlib only)
=======================================================

Synchronous sqlite3 layer (stdlib — no aiosqlite) for the GHL agent's local
state. Modeled on ``monetizing-agent/memory.py`` and ``eva-state/memory.py``
(the reference governed append-only-ledger modules).

Tables:

  memory              intelligence-layer key/value store (key, value, ts, source)
  agent_runs          one row per build/capture run (observe->act->learn loop)
  directive_versions  version history of the module's live directive
  lead_events         APPEND-ONLY ledger of lead lifecycle events (immutable)
  funnel_artifacts    APPEND-ONLY record of one-time-build artifacts (idempotency)

The ``lead_events`` ledger is the audit trail for every lead touch. Its identity
columns are frozen by an immutability trigger; only the lifecycle ``status``
column may transition. DELETEs are blocked outright. Corrections are written as
NEW events carrying ``supersedes_event_id`` — never edits or deletes, exactly as
the state-ledger doctrine requires.

``funnel_artifacts`` is likewise append-only: each row records that a piece of
the one-time build (pipeline, calendar, custom_field, template, workflow) was
created or found, so ``/funnel/status`` can answer without re-hitting GHL and the
build stays idempotent across restarts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "ghl_agent.db")

# Lead lifecycle event types (also the vocabulary emitted to the state ledger).
EVENT_LEAD_CAPTURED = "lead_captured"
EVENT_TOUCH_SENT = "touch_sent"
EVENT_LEAD_ENGAGED = "lead_engaged"
EVENT_DEMO_BOOKED = "demo_booked"
EVENT_DEMO_HELD = "demo_held"
EVENT_CLOSED = "closed"

LEAD_EVENT_TYPES = {
    EVENT_LEAD_CAPTURED,
    EVENT_TOUCH_SENT,
    EVENT_LEAD_ENGAGED,
    EVENT_DEMO_BOOKED,
    EVENT_DEMO_HELD,
    EVENT_CLOSED,
}

# Lead event lifecycle status.
STATUS_OPEN = "open"
STATUS_SUPERSEDED = "superseded"

# Funnel artifact kinds (the one-time build pieces).
ARTIFACT_PIPELINE = "pipeline"
ARTIFACT_CALENDAR = "calendar"
ARTIFACT_CUSTOM_FIELD = "custom_field"
ARTIFACT_TEMPLATE = "template"
ARTIFACT_WORKFLOW = "workflow"


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
    timestamp  TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT '',    -- build | capture | webhook
    inputs     TEXT NOT NULL DEFAULT '{}',
    outputs    TEXT NOT NULL DEFAULT '{}',
    tokens     INTEGER NOT NULL DEFAULT 0,
    notes      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS directive_versions (
    id         TEXT PRIMARY KEY,
    version    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- APPEND-ONLY ledger of lead lifecycle events.
CREATE TABLE IF NOT EXISTS lead_events (
    event_id            TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    contact_id          TEXT NOT NULL DEFAULT '',
    email               TEXT NOT NULL DEFAULT '',
    event_type          TEXT NOT NULL DEFAULT '',
    summary             TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT '',   -- eva-acquisition | ghl-webhook | cli
    payload_json        TEXT NOT NULL DEFAULT '{}',
    supersedes_event_id TEXT,
    status              TEXT NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_lead_events_contact ON lead_events(contact_id);
CREATE INDEX IF NOT EXISTS idx_lead_events_type    ON lead_events(event_type);
CREATE INDEX IF NOT EXISTS idx_lead_events_email   ON lead_events(email);

-- Immutability: identity/content columns are frozen once written; only the
-- lifecycle ``status`` column may change (corrections are written as NEW events).
-- DELETE is blocked outright.
CREATE TRIGGER IF NOT EXISTS lead_events_no_identity_update
BEFORE UPDATE ON lead_events
WHEN
    OLD.event_id            != NEW.event_id            OR
    OLD.timestamp           != NEW.timestamp           OR
    OLD.contact_id          != NEW.contact_id          OR
    OLD.email               != NEW.email               OR
    OLD.event_type          != NEW.event_type          OR
    OLD.summary             != NEW.summary             OR
    OLD.source              != NEW.source              OR
    OLD.payload_json        != NEW.payload_json        OR
    IFNULL(OLD.supersedes_event_id,'') != IFNULL(NEW.supersedes_event_id,'')
BEGIN
    SELECT RAISE(ABORT, 'lead_events is append-only: identity columns are immutable; write a correction event instead');
END;

CREATE TRIGGER IF NOT EXISTS lead_events_no_delete
BEFORE DELETE ON lead_events
BEGIN
    SELECT RAISE(ABORT, 'lead_events is append-only: rows cannot be deleted');
END;

-- APPEND-ONLY record of one-time-build artifacts (idempotency source of truth).
CREATE TABLE IF NOT EXISTS funnel_artifacts (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT '',   -- pipeline | calendar | custom_field | template | workflow
    name          TEXT NOT NULL DEFAULT '',
    external_id   TEXT NOT NULL DEFAULT '',    -- GHL-side id (or '' if manual/unavailable)
    action        TEXT NOT NULL DEFAULT '',    -- created | skipped | manual_required
    detail_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_funnel_kind ON funnel_artifacts(kind, name);

CREATE TRIGGER IF NOT EXISTS funnel_artifacts_no_update
BEFORE UPDATE ON funnel_artifacts
BEGIN
    SELECT RAISE(ABORT, 'funnel_artifacts is append-only: rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS funnel_artifacts_no_delete
BEFORE DELETE ON funnel_artifacts
BEGIN
    SELECT RAISE(ABORT, 'funnel_artifacts is append-only: rows cannot be deleted');
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


def _loads(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}
    return v if v is not None else {}


# ---------------------------------------------------------------------------
# memory (intelligence-layer key/value)
# ---------------------------------------------------------------------------

def remember(key: str, value: Any, source: str = "", path: str = DB_PATH) -> None:
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

def save_run(kind: str, inputs: dict, outputs: dict, tokens: int = 0,
             notes: str = "", path: str = DB_PATH) -> str:
    run_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO agent_runs (id, timestamp, kind, inputs, outputs, tokens, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, _now(), kind, json.dumps(inputs, default=str),
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
# lead_events (append-only ledger)
# ---------------------------------------------------------------------------

def record_lead_event(
    *,
    event_type: str,
    contact_id: str = "",
    email: str = "",
    summary: str = "",
    source: str = "eva-acquisition",
    payload: Optional[dict] = None,
    supersedes_event_id: Optional[str] = None,
    status: str = STATUS_OPEN,
    timestamp: Optional[str] = None,
    path: str = DB_PATH,
) -> str:
    """Append one lead lifecycle event. Returns the new event_id.

    If ``supersedes_event_id`` is given, the prior event is marked superseded via
    its only mutable column (``status``) — the corrections-as-new-events rule.
    """
    event_id = str(uuid.uuid4())
    ts = timestamp or _now()
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO lead_events
                (event_id, timestamp, contact_id, email, event_type, summary,
                 source, payload_json, supersedes_event_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, ts, contact_id, email, event_type, summary, source,
             json.dumps(payload or {}, default=str), supersedes_event_id, status),
        )
        if supersedes_event_id:
            conn.execute(
                "UPDATE lead_events SET status = ? WHERE event_id = ?",
                (STATUS_SUPERSEDED, supersedes_event_id),
            )
        conn.commit()
    finally:
        conn.close()
    return event_id


def list_lead_events(
    *,
    contact_id: Optional[str] = None,
    email: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: Optional[int] = None,
    path: str = DB_PATH,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    for col, val in (("contact_id", contact_id), ("email", email),
                     ("event_type", event_type)):
        if val is not None:
            clauses.append(f"{col} = ?")
            params.append(val)
    sql = "SELECT * FROM lead_events"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY timestamp DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    conn = _connect(path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        conn.close()


def _row_to_event(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["payload"] = _loads(d.pop("payload_json", "{}"))
    return d


def lead_event_count(path: str = DB_PATH) -> int:
    conn = _connect(path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM lead_events").fetchone()[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# funnel_artifacts (append-only build record)
# ---------------------------------------------------------------------------

def record_artifact(
    *,
    kind: str,
    name: str,
    external_id: str = "",
    action: str = "created",
    detail: Optional[dict] = None,
    path: str = DB_PATH,
) -> str:
    art_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO funnel_artifacts
                (id, created_at, kind, name, external_id, action, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (art_id, _now(), kind, name, external_id, action,
             json.dumps(detail or {}, default=str)),
        )
        conn.commit()
    finally:
        conn.close()
    return art_id


def list_artifacts(kind: Optional[str] = None, path: str = DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM funnel_artifacts WHERE kind = ? ORDER BY created_at DESC",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM funnel_artifacts ORDER BY created_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = _loads(d.pop("detail_json", "{}"))
            out.append(d)
        return out
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
