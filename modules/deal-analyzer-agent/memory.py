"""
EVA Deal Analyzer Agent — persistent memory (SQLite, stdlib only)
=================================================================

Synchronous sqlite3 layer (deliberately stdlib — no aiosqlite dependency) for
the agent's long-term memory. Four tables:

  deals              scored deals + the full score JSON blob
  agent_runs         one row per observe->reason->act->learn loop run
  learnings          outcome feedback (passed / LOI / closed) used to recalibrate
  directive_versions version history of the agent's live directive

This is the substrate the `learn()` step writes to and the directive-sync bridge
(next phase) reads from.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    category_v2   TEXT NOT NULL DEFAULT '',
    overall_score REAL NOT NULL DEFAULT 0,
    score_json    TEXT NOT NULL DEFAULT '{}',   -- full DealV7.model_dump()
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          TEXT PRIMARY KEY,
    deal_id     TEXT NOT NULL DEFAULT '',
    timestamp   TEXT NOT NULL,
    inputs      TEXT NOT NULL DEFAULT '{}',      -- observed inputs (deal + enrichment)
    outputs     TEXT NOT NULL DEFAULT '{}',      -- reason/act outputs (scores)
    tokens      INTEGER NOT NULL DEFAULT 0,       -- LLM tokens used (0 until wired)
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS learnings (
    id           TEXT PRIMARY KEY,
    deal_id      TEXT NOT NULL DEFAULT '',
    stage        TEXT NOT NULL DEFAULT '',        -- pipeline stage at outcome
    outcome      TEXT NOT NULL DEFAULT '',        -- passed | loi | closed | dead
    lesson       TEXT NOT NULL DEFAULT '',
    weight_delta TEXT NOT NULL DEFAULT '{}',      -- proposed {dimension: delta} adjustments
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS directive_versions (
    id         TEXT PRIMARY KEY,
    version    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_observations (
    id            TEXT PRIMARY KEY,
    deal_id       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT '',   -- CostTier at capture (SHORTLIST|LOG_ONLY)
    v7_score      REAL NOT NULL DEFAULT 0,     -- authoritative deterministic score
    features      TEXT NOT NULL DEFAULT '{}',  -- scored DealV7 dump (labeled features)
    enrichment    TEXT NOT NULL DEFAULT '{}',  -- enrichment kwargs used
    brain_output  TEXT NOT NULL DEFAULT '{}',  -- advisory + provider + tokens (if any)
    gate_trace    TEXT NOT NULL DEFAULT '{}',  -- radar reasons + routing decision
    known_outcome TEXT NOT NULL DEFAULT '{}'   -- closed-deal label if present
);

-- Canonical per-agent memory + append-only ledger (Architecture Directive).
-- Schema + immutability triggers copied verbatim from the reference modules
-- (modules/postcards, modules/meet-ingest).
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


def init_db(path: str = DB_PATH) -> None:
    """Create all tables if absent."""
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
# deals
# ---------------------------------------------------------------------------

def save_deal(deal_dump: dict, path: str = DB_PATH) -> None:
    """Upsert a scored deal (full DealV7.model_dump()) into the deals table."""
    conn = _connect(path)
    try:
        ts = _now()
        conn.execute(
            """
            INSERT INTO deals (id, name, category, category_v2, overall_score,
                               score_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                category_v2=excluded.category_v2,
                overall_score=excluded.overall_score,
                score_json=excluded.score_json,
                updated_at=excluded.updated_at
            """,
            (
                deal_dump.get("id"),
                deal_dump.get("name", ""),
                deal_dump.get("category", ""),
                deal_dump.get("category_v2", ""),
                float(deal_dump.get("overall_score", 0.0)),
                json.dumps(deal_dump, default=str),
                ts,
                ts,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_deal(deal_id: str, path: str = DB_PATH) -> Optional[dict]:
    """Return the full stored score JSON for a deal, or None."""
    conn = _connect(path)
    try:
        row = conn.execute("SELECT score_json FROM deals WHERE id = ?", (deal_id,)).fetchone()
        return json.loads(row["score_json"]) if row else None
    finally:
        conn.close()


def list_deals(path: str = DB_PATH) -> list[dict]:
    """Return all stored deals (id, name, scores) ordered by overall_score desc."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT id, name, category, category_v2, overall_score, updated_at "
            "FROM deals ORDER BY overall_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# agent_runs
# ---------------------------------------------------------------------------

def save_run(
    deal_id: str,
    inputs: dict,
    outputs: dict,
    tokens: int = 0,
    notes: str = "",
    path: str = DB_PATH,
) -> str:
    """Persist one agent loop run. Returns the run id."""
    run_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO agent_runs (id, deal_id, timestamp, inputs, outputs, tokens, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, deal_id, _now(),
                json.dumps(inputs, default=str),
                json.dumps(outputs, default=str),
                int(tokens), notes,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def list_runs(deal_id: Optional[str] = None, path: str = DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        if deal_id:
            rows = conn.execute(
                "SELECT * FROM agent_runs WHERE deal_id = ? ORDER BY timestamp DESC",
                (deal_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_runs ORDER BY timestamp DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# learnings
# ---------------------------------------------------------------------------

def record_learning(
    deal_id: str,
    stage: str,
    outcome: str,
    lesson: str,
    weight_delta: Optional[dict] = None,
    path: str = DB_PATH,
) -> str:
    """Record an outcome-feedback learning. Returns the learning id."""
    learning_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO learnings (id, deal_id, stage, outcome, lesson, weight_delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                learning_id, deal_id, stage, outcome, lesson,
                json.dumps(weight_delta or {}, default=str), _now(),
            ),
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
    """Append a directive version snapshot. Returns the row id."""
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
# training_observations (testing-mode labeled records)
# ---------------------------------------------------------------------------

def save_training_observation(
    deal_id: str,
    tier: str,
    v7_score: float,
    features: dict,
    enrichment: dict,
    brain_output: dict,
    gate_trace: dict,
    known_outcome: Optional[dict] = None,
    path: str = DB_PATH,
) -> str:
    """Persist one labeled training_observation (testing mode). Returns its id.

    Captures the full picture for later gate calibration: features (scored deal),
    the enrichment used, the deterministic v7 score, any brain output, the gate
    trace (radar reasons + routing), and an optional closed-deal known_outcome.
    """
    obs_id = str(uuid.uuid4())
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO training_observations
                (id, deal_id, created_at, tier, v7_score, features, enrichment,
                 brain_output, gate_trace, known_outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs_id, deal_id, _now(), tier, float(v7_score or 0.0),
                json.dumps(features, default=str),
                json.dumps(enrichment, default=str),
                json.dumps(brain_output, default=str),
                json.dumps(gate_trace, default=str),
                json.dumps(known_outcome or {}, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return obs_id


def list_training_observations(path: str = DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM training_observations ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# memory (per-agent knowledge) + append-only ledger accessors
# ---------------------------------------------------------------------------

def set_memory(key: str, value: str, source: str = "system",
               path: str = DB_PATH) -> dict:
    init_db(path)
    now = _now()
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, ts=excluded.ts, source=excluded.source""",
            (key, value, now, source),
        )
        conn.commit()
    finally:
        conn.close()
    return {"key": key, "value": value, "ts": now, "source": source}


def get_memory(key: str, default: Optional[str] = None,
               path: str = DB_PATH) -> Optional[str]:
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def list_memory(path: str = DB_PATH) -> list[dict]:
    init_db(path)
    conn = _connect(path)
    try:
        return [dict(r) for r in
                conn.execute("SELECT * FROM memory ORDER BY key").fetchall()]
    finally:
        conn.close()


def append_ledger(event_type: str, entity_type: str = "", entity_id: str = "",
                  actor: str = "", details: Optional[dict] = None,
                  path: str = DB_PATH) -> dict:
    init_db(path)
    row = {
        "id": str(uuid.uuid4()), "ts": _now(), "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id, "actor": actor,
        "details_json": json.dumps(details or {}),
    }
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO ledger
               (id, ts, event_type, entity_type, entity_id, actor, details_json)
               VALUES (:id,:ts,:event_type,:entity_type,:entity_id,:actor,:details_json)""",
            row,
        )
        conn.commit()
    finally:
        conn.close()
    out = dict(row)
    out["details"] = json.loads(out.pop("details_json"))
    return out


def query_ledger(event_type: Optional[str] = None,
                 path: str = DB_PATH) -> list[dict]:
    init_db(path)
    q, params = "SELECT * FROM ledger", []
    if event_type:
        q += " WHERE event_type=?"
        params.append(event_type)
    q += " ORDER BY ts ASC"
    conn = _connect(path)
    try:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
    return rows
