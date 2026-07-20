"""
EVA Remote-Bridge — SQLite persistence (stdlib sqlite3, sync).

Two tables:
  * ``instructions``      — one row per remote instruction (the mutable status
    record: received → dispatched → complete | failed).
  * ``instruction_ledger`` — an append-only audit trail with BEFORE UPDATE /
    BEFORE DELETE immutability triggers, copied from the pattern used in
    ``modules/channels`` (``channels_ledger``) and ``modules/eva-state``.

Also a ``memory`` table (Agent Intelligence Layer contract) and a graceful
``docs/MISSION.md`` / ``docs/CURRENT_GOALS.md`` read at startup (no-op if absent).

Stdlib only; the DB lives beside this module and is gitignored (*.db).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "REMOTE_BRIDGE_DB",
    os.path.join(os.path.dirname(__file__), "remote_bridge.db"),
)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Instruction lifecycle statuses.
STATUS_RECEIVED = "received"
STATUS_DISPATCHED = "dispatched"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

LIST_MAX = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS instructions (
    id                    TEXT PRIMARY KEY,
    goal                  TEXT NOT NULL DEFAULT '',
    context_json          TEXT NOT NULL DEFAULT '{}',
    status                TEXT NOT NULL DEFAULT 'received',
    dispatch_result_json  TEXT NOT NULL DEFAULT '{}',
    error                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruction_ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_instructions_status ON instructions(status);
CREATE INDEX IF NOT EXISTS idx_instructions_created ON instructions(created_at);

-- The instruction ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS instruction_ledger_no_update
BEFORE UPDATE ON instruction_ledger
BEGIN
    SELECT RAISE(ABORT, 'instruction_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS instruction_ledger_no_delete
BEFORE DELETE ON instruction_ledger
BEGIN
    SELECT RAISE(ABORT, 'instruction_ledger is append-only');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Thin sync sqlite3 data-access layer. Opens a fresh connection per op."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- instructions -------------------------------------------------------

    def create_instruction(self, goal: str, context: Optional[dict] = None) -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "goal": goal,
            "context_json": json.dumps(context or {}),
            "status": STATUS_RECEIVED,
            "dispatch_result_json": "{}",
            "error": "",
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO instructions
                   (id, goal, context_json, status, dispatch_result_json,
                    error, created_at, updated_at)
                   VALUES (:id, :goal, :context_json, :status,
                           :dispatch_result_json, :error, :created_at, :updated_at)""",
                row,
            )
        return self._hydrate(row)

    def get_instruction(self, instruction_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM instructions WHERE id = ?", (instruction_id,)
            ).fetchone()
        return self._hydrate(dict(r)) if r else None

    def list_instructions(self, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), LIST_MAX))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM instructions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._hydrate(dict(r)) for r in rows]

    def update_instruction(self, instruction_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_instruction(instruction_id)
        cols = dict(fields)
        if "dispatch_result" in cols:
            cols["dispatch_result_json"] = json.dumps(cols.pop("dispatch_result"))
        if "context" in cols:
            cols["context_json"] = json.dumps(cols.pop("context"))
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = instruction_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE instructions SET {assignments} WHERE id = :id", cols
            )
        return self.get_instruction(instruction_id)

    @staticmethod
    def _hydrate(row: dict) -> dict:
        out = dict(row)
        for raw, cooked in (("context_json", "context"),
                            ("dispatch_result_json", "dispatch_result")):
            try:
                out[cooked] = json.loads(out.get(raw) or "{}")
            except (json.JSONDecodeError, TypeError):
                out[cooked] = {}
        return out

    # -- ledger (append-only) ----------------------------------------------

    def append_ledger(self, event_type: str, entity_type: str = "instruction",
                      entity_id: str = "", actor: str = "",
                      details: Optional[dict] = None) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor": actor,
            "details_json": json.dumps(details or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO instruction_ledger
                   (id, ts, event_type, entity_type, entity_id, actor, details_json)
                   VALUES (:id, :ts, :event_type, :entity_type, :entity_id,
                           :actor, :details_json)""",
                row,
            )
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def query_ledger(self, entity_id: Optional[str] = None) -> list[dict]:
        clause = "WHERE entity_id = ?" if entity_id else ""
        params = (entity_id,) if entity_id else ()
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM instruction_ledger {clause} ORDER BY ts ASC",
                params,
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
            out.append(d)
        return out

    # -- memory (Agent Intelligence Layer) ----------------------------------

    def remember(self, key: str, value: str, source: str = "agent") -> None:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source)
                   VALUES (:key, :value, :ts, :source)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value, ts = excluded.ts, source = excluded.source""",
                row,
            )

    def recall(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return r["value"] if r else None


def read_mission_and_goals() -> dict:
    """Read the shared north-star docs at startup. Graceful no-op if absent."""
    out = {"mission": "", "current_goals": ""}
    for key, rel in (("mission", "docs/MISSION.md"),
                     ("current_goals", "docs/CURRENT_GOALS.md")):
        try:
            with open(os.path.join(_REPO_ROOT, rel), "r", encoding="utf-8") as fh:
                out[key] = fh.read()
        except (FileNotFoundError, OSError):
            out[key] = ""
    return out


__all__ = [
    "Store", "read_mission_and_goals", "DB_PATH",
    "STATUS_RECEIVED", "STATUS_DISPATCHED", "STATUS_COMPLETE", "STATUS_FAILED",
]
