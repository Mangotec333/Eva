"""
EVA State Ledger — persistent append-only event store (SQLite, stdlib only)
==========================================================================

The governed single source of truth for state and history *across* all Eva
agents, sessions, and surfaces. Modeled on ``monetizing-agent/memory.py`` (the
reference append-only-ledger-with-immutability-trigger module) and generalized
from packaged-plays to arbitrary events.

Core primitive: an **append-only** ``events`` table. Every meaningful thing that
happens is an event. Corrections are *new* events (``correction_event`` /
``supersedes_event_id`` / ``corrects_event_id``) — never an edit or a delete.

Tables:

  memory                intelligence-layer key/value store (key, value, ts, source)
  agent_runs            one row per importer/tick run (observe->act->learn loop)
  directive_versions    version history of the module's live directive
  events                APPEND-ONLY event ledger (immutability trigger)

Derived SQLite VIEWS (generated from the ledger, never hand-maintained):

  project_state_view    latest non-superseded status per project
  task_state_view       latest non-superseded status per task entity
  daily_priority_view   open blockers + deadlines + coined-term traction signals
  coined_terms_view     per-coined-term rollup (references, engagement, traction)

Immutability contract (mirrors monetizing-agent): the identity/content columns
of an event are frozen on insert; only the lifecycle ``status`` column may
transition (and even that is normally done by writing a correction event, not by
mutating in place). DELETE is blocked outright.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

# Event lifecycle statuses (an event's *current* standing).
STATUS_OPEN = "open"
STATUS_ACTIVE = "active"
STATUS_IN_PROGRESS = "in_progress"
STATUS_LIVE = "live"
STATUS_PLANNED = "planned"
STATUS_BLOCKED = "blocked"
STATUS_DONE = "done"
STATUS_DROPPED = "dropped"
STATUS_SUPERSEDED = "superseded"

# Event types (the doctrine's vocabulary + first-class coined_term events).
EVENT_TYPES = {
    "decision_made",
    "directive_created",
    "task_created",
    "task_status_changed",
    "agent_run_started",
    "agent_run_completed",
    "artifact_created",
    "approval_requested",
    "approval_granted",
    "blocker_added",
    "blocker_resolved",
    "outcome_recorded",
    "project_status_changed",
    "external_link_added",
    "priority_changed",
    "correction_event",
    # First-class coined-term events (Vineet's USP — see the coined-terms directive).
    "coined_term_created",
    "coined_term_referenced",
}

# First-class entity types. ``coined_term`` is a REQUIRED first-class entity.
ENTITY_TYPES = {
    "project", "module", "task", "blocker", "decision", "artifact",
    "approval", "agent", "interface", "deal", "coined_term",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    """Slugify a coined term (or any label) into a stable entity_id.

    e.g. 'ScissorHands' -> 'scissorhands', 'The Voice Lock' -> 'the-voice-lock'.
    """
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower())
    return s.strip("-") or "unknown"


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

-- APPEND-ONLY event ledger. Every meaningful state change is one row.
CREATE TABLE IF NOT EXISTS events (
    event_id            TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    actor               TEXT NOT NULL DEFAULT '',   -- Vineet | Eva | subagent | system
    source_surface      TEXT NOT NULL DEFAULT '',   -- Perplexity | Command Center | cron | GitHub PR | Drive | Slack
    project             TEXT NOT NULL DEFAULT '',
    track               TEXT NOT NULL DEFAULT '',
    entity_type         TEXT NOT NULL DEFAULT '',
    entity_id           TEXT NOT NULL DEFAULT '',
    event_type          TEXT NOT NULL DEFAULT '',
    summary             TEXT NOT NULL DEFAULT '',
    payload_json        TEXT NOT NULL DEFAULT '{}',
    evidence_urls       TEXT NOT NULL DEFAULT '[]',
    supersedes_event_id TEXT,
    corrects_event_id   TEXT,
    confidence          REAL NOT NULL DEFAULT 1.0,
    status              TEXT NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_events_project     ON events(project);
CREATE INDEX IF NOT EXISTS idx_events_entity      ON events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_type        ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_supersedes  ON events(supersedes_event_id);

-- Immutability: identity/content columns are frozen once written; only the
-- lifecycle ``status`` column may change (and normally corrections are written
-- as NEW events). DELETE is blocked outright.
CREATE TRIGGER IF NOT EXISTS events_no_identity_update
BEFORE UPDATE ON events
WHEN
    OLD.event_id            != NEW.event_id            OR
    OLD.timestamp           != NEW.timestamp           OR
    OLD.actor               != NEW.actor               OR
    OLD.source_surface      != NEW.source_surface      OR
    OLD.project             != NEW.project             OR
    OLD.track               != NEW.track               OR
    OLD.entity_type         != NEW.entity_type         OR
    OLD.entity_id           != NEW.entity_id           OR
    OLD.event_type          != NEW.event_type          OR
    OLD.summary             != NEW.summary             OR
    OLD.payload_json        != NEW.payload_json        OR
    OLD.evidence_urls       != NEW.evidence_urls       OR
    IFNULL(OLD.supersedes_event_id,'') != IFNULL(NEW.supersedes_event_id,'') OR
    IFNULL(OLD.corrects_event_id,'')   != IFNULL(NEW.corrects_event_id,'')   OR
    OLD.confidence          != NEW.confidence
BEGIN
    SELECT RAISE(ABORT, 'events is append-only: identity columns are immutable; write a correction_event instead');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events is append-only: rows cannot be deleted');
END;
"""

# Derived views are (re)created after the base tables so schema changes to the
# view definitions take effect on every init.
_VIEWS = """
DROP VIEW IF EXISTS superseded_ids;
CREATE VIEW superseded_ids AS
    SELECT supersedes_event_id AS event_id FROM events
    WHERE supersedes_event_id IS NOT NULL AND supersedes_event_id != '';

-- Latest LIVE (non-superseded) event per project — the current project status.
DROP VIEW IF EXISTS project_state_view;
CREATE VIEW project_state_view AS
    SELECT e.project        AS project,
           e.status         AS status,
           e.summary        AS summary,
           e.event_type     AS event_type,
           e.timestamp      AS updated_at,
           e.event_id       AS event_id
    FROM events e
    WHERE e.project != ''
      AND e.event_id NOT IN (SELECT event_id FROM superseded_ids)
      AND e.timestamp = (
          SELECT MAX(e2.timestamp) FROM events e2
          WHERE e2.project = e.project
            AND e2.event_id NOT IN (SELECT event_id FROM superseded_ids)
      );

-- Latest LIVE state per task entity.
DROP VIEW IF EXISTS task_state_view;
CREATE VIEW task_state_view AS
    SELECT e.entity_id      AS entity_id,
           e.project        AS project,
           e.summary        AS summary,
           e.status         AS status,
           e.timestamp      AS updated_at,
           e.event_id       AS event_id
    FROM events e
    WHERE e.entity_type = 'task'
      AND e.event_id NOT IN (SELECT event_id FROM superseded_ids)
      AND e.timestamp = (
          SELECT MAX(e2.timestamp) FROM events e2
          WHERE e2.entity_type = 'task' AND e2.entity_id = e.entity_id
            AND e2.event_id NOT IN (SELECT event_id FROM superseded_ids)
      );

-- Per-coined-term rollup: reference count, last reference, total engagement,
-- and any productization flags recorded on the term's events.
DROP VIEW IF EXISTS coined_terms_view;
CREATE VIEW coined_terms_view AS
    SELECT
        c.entity_id AS entity_id,
        json_extract(c.payload_json, '$.term')       AS term,
        json_extract(c.payload_json, '$.domain')     AS domain,
        json_extract(c.payload_json, '$.definition') AS definition,
        c.timestamp AS coined_date,
        (SELECT COUNT(*) FROM events r
             WHERE r.entity_type = 'coined_term' AND r.entity_id = c.entity_id
               AND r.event_type = 'coined_term_referenced') AS reference_count,
        (SELECT MAX(r.timestamp) FROM events r
             WHERE r.entity_type = 'coined_term' AND r.entity_id = c.entity_id
               AND r.event_type = 'coined_term_referenced') AS last_referenced,
        (SELECT COALESCE(SUM(CAST(json_extract(r.payload_json, '$.engagement_metrics.total') AS REAL)), 0)
             FROM events r
             WHERE r.entity_type = 'coined_term' AND r.entity_id = c.entity_id
               AND r.event_type = 'coined_term_referenced') AS total_engagement,
        (SELECT GROUP_CONCAT(json_extract(p.payload_json, '$.productization_flag'), ', ')
             FROM events p
             WHERE p.entity_type = 'coined_term' AND p.entity_id = c.entity_id
               AND json_extract(p.payload_json, '$.productization_flag') IS NOT NULL)
             AS productization_flags
    FROM events c
    WHERE c.entity_type = 'coined_term'
      AND c.event_type = 'coined_term_created';

-- Daily priorities: open blockers, deadline-bearing tasks, and coined terms with
-- rising traction (>=1 reference) — the last connects to the Monetizing Agent's
-- Content-to-offer play (coined-term traction = a monetization signal).
DROP VIEW IF EXISTS daily_priority_view;
CREATE VIEW daily_priority_view AS
    -- Open blockers (highest priority)
    SELECT 'blocker'  AS kind,
           e.project  AS project,
           e.entity_id AS entity_id,
           e.summary  AS summary,
           100        AS priority,
           e.timestamp AS updated_at
    FROM events e
    WHERE e.entity_type = 'blocker' AND e.status = 'blocked'
      AND e.event_id NOT IN (SELECT event_id FROM superseded_ids)
      AND e.event_id NOT IN (
          SELECT corrects_event_id FROM events
          WHERE event_type = 'blocker_resolved' AND corrects_event_id IS NOT NULL)
    UNION ALL
    -- Tasks carrying a deadline in their payload
    SELECT 'deadline' AS kind,
           e.project  AS project,
           e.entity_id AS entity_id,
           e.summary  AS summary,
           80         AS priority,
           e.timestamp AS updated_at
    FROM events e
    WHERE e.entity_type = 'task'
      AND json_extract(e.payload_json, '$.deadline') IS NOT NULL
      AND e.status NOT IN ('done', 'dropped')
      AND e.event_id NOT IN (SELECT event_id FROM superseded_ids)
    UNION ALL
    -- Coined terms with rising traction (monetization signal)
    SELECT 'coined_term_traction' AS kind,
           'Personal Brand'       AS project,
           v.entity_id            AS entity_id,
           (v.term || ' — ' || v.reference_count || ' refs, ' ||
            CAST(v.total_engagement AS INTEGER) || ' engagement') AS summary,
           (50 + MIN(v.reference_count * 5, 40)) AS priority,
           COALESCE(v.last_referenced, v.coined_date) AS updated_at
    FROM coined_terms_view v
    WHERE v.reference_count >= 1;
"""


def init_db(path: str = DB_PATH) -> None:
    """Create all tables, triggers, and views if absent (idempotent)."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.executescript(_VIEWS)
        conn.commit()
    finally:
        conn.close()


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# events (append-only ledger)
# ---------------------------------------------------------------------------

def append_event(
    *,
    event_type: str,
    summary: str = "",
    actor: str = "system",
    source_surface: str = "",
    project: str = "",
    track: str = "",
    entity_type: str = "",
    entity_id: str = "",
    payload: Optional[dict] = None,
    evidence_urls: Optional[list] = None,
    supersedes_event_id: Optional[str] = None,
    corrects_event_id: Optional[str] = None,
    confidence: float = 1.0,
    status: str = STATUS_OPEN,
    timestamp: Optional[str] = None,
    path: str = DB_PATH,
) -> str:
    """Append one event to the ledger. Returns the new event_id.

    If ``supersedes_event_id`` is given, the superseded event is marked
    ``superseded`` via its only mutable column (``status``) — the doctrine's
    corrections-as-new-events rule.
    """
    event_id = str(uuid.uuid4())
    ts = timestamp or _now()
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO events
                (event_id, timestamp, actor, source_surface, project, track,
                 entity_type, entity_id, event_type, summary, payload_json,
                 evidence_urls, supersedes_event_id, corrects_event_id,
                 confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, ts, actor, source_surface, project, track,
             entity_type, entity_id, event_type, summary,
             json.dumps(payload or {}, default=str),
             json.dumps(evidence_urls or [], default=str),
             supersedes_event_id, corrects_event_id, float(confidence), status),
        )
        if supersedes_event_id:
            # Only the lifecycle column changes → satisfies the immutability trigger.
            conn.execute(
                "UPDATE events SET status = ? WHERE event_id = ?",
                (STATUS_SUPERSEDED, supersedes_event_id),
            )
        conn.commit()
    finally:
        conn.close()
    return event_id


def correct_event(
    original_event_id: str,
    *,
    summary: str,
    status: str = STATUS_DROPPED,
    actor: str = "Eva",
    source_surface: str = "",
    payload: Optional[dict] = None,
    evidence_urls: Optional[list] = None,
    path: str = DB_PATH,
) -> str:
    """Write a ``correction_event`` that supersedes a prior event.

    Never edits or deletes the original — the correction carries the original's
    project/track/entity so views resolve to the corrected standing, and the
    original is marked ``superseded``.
    """
    original = get_event(original_event_id, path)
    if original is None:
        raise ValueError(f"cannot correct unknown event {original_event_id!r}")
    return append_event(
        event_type="correction_event",
        summary=summary,
        actor=actor,
        source_surface=source_surface,
        project=original["project"],
        track=original["track"],
        entity_type=original["entity_type"],
        entity_id=original["entity_id"],
        payload=payload or {},
        evidence_urls=evidence_urls or [],
        supersedes_event_id=original_event_id,
        corrects_event_id=original_event_id,
        status=status,
        path=path,
    )


def get_event(event_id: str, path: str = DB_PATH) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None
    finally:
        conn.close()


def list_events(
    *,
    project: Optional[str] = None,
    track: Optional[str] = None,
    entity_type: Optional[str] = None,
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    entity_id: Optional[str] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    path: str = DB_PATH,
) -> list[dict]:
    """Filtered, most-recent-first event query."""
    clauses: list[str] = []
    params: list[Any] = []
    for col, val in (
        ("project", project), ("track", track), ("entity_type", entity_type),
        ("event_type", event_type), ("actor", actor), ("entity_id", entity_id),
    ):
        if val is not None:
            clauses.append(f"{col} = ?")
            params.append(val)
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since)
    sql = "SELECT * FROM events"
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
    d["evidence_urls"] = _loads(d.get("evidence_urls", "[]"))
    return d


def _loads(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}
    return v if v is not None else {}


# ---------------------------------------------------------------------------
# Derived-view reads
# ---------------------------------------------------------------------------

def _view_rows(view: str, path: str = DB_PATH, order: str = "") -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute(f"SELECT * FROM {view} {order}").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def project_state(path: str = DB_PATH) -> list[dict]:
    return _view_rows("project_state_view", path, "ORDER BY project")


def task_state(path: str = DB_PATH) -> list[dict]:
    return _view_rows("task_state_view", path, "ORDER BY updated_at DESC")


def daily_priorities(path: str = DB_PATH) -> list[dict]:
    return _view_rows("daily_priority_view", path, "ORDER BY priority DESC, updated_at DESC")


def coined_terms(path: str = DB_PATH) -> list[dict]:
    return _view_rows("coined_terms_view", path,
                      "ORDER BY reference_count DESC, total_engagement DESC")


def open_blockers(path: str = DB_PATH) -> list[dict]:
    """Blockers whose most recent event still stands as blocked."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM events e
            WHERE e.entity_type = 'blocker' AND e.status = 'blocked'
              AND e.event_id NOT IN (SELECT event_id FROM superseded_ids)
            ORDER BY e.timestamp DESC
            """
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        conn.close()


def pending_approvals(path: str = DB_PATH) -> list[dict]:
    """approval_requested events not yet answered by an approval_granted."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM events e
            WHERE e.event_type = 'approval_requested'
              AND e.entity_id NOT IN (
                  SELECT entity_id FROM events WHERE event_type = 'approval_granted')
            ORDER BY e.timestamp DESC
            """
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        conn.close()


def recent_decisions(limit: int = 20, path: str = DB_PATH) -> list[dict]:
    return list_events(event_type="decision_made", limit=limit, path=path)


def agent_health(path: str = DB_PATH) -> list[dict]:
    """Latest agent_run_completed per agent entity (a cross-agent liveness view)."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            """
            SELECT e.entity_id AS agent, e.status AS status, e.summary AS summary,
                   e.timestamp AS last_run, e.source_surface AS source_surface
            FROM events e
            WHERE e.event_type IN ('agent_run_completed', 'agent_run_started')
              AND e.timestamp = (
                  SELECT MAX(e2.timestamp) FROM events e2
                  WHERE e2.entity_id = e.entity_id
                    AND e2.event_type IN ('agent_run_completed', 'agent_run_started'))
            GROUP BY e.entity_id
            ORDER BY last_run DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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

def save_run(inputs: dict, outputs: dict, tokens: int = 0, notes: str = "",
             path: str = DB_PATH) -> str:
    run_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO agent_runs (id, timestamp, inputs, outputs, tokens, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, _now(), json.dumps(inputs, default=str),
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


def event_count(path: str = DB_PATH) -> int:
    conn = _connect(path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
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
