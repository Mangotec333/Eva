"""
EVA Video Generator — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/postcards`` convention: standard-library ``sqlite3`` (no
aiosqlite), so the service is fully runnable offline. The ``video_ledger`` table
is made append-only with BEFORE UPDATE / BEFORE DELETE triggers copied exactly
from postcards' ``publish_ledger``.

Also provides the Agent Intelligence Layer's ``memory`` table (per-agent
key-value context read on task start, written on decision/learning) and reads
``docs/MISSION.md`` + ``docs/CURRENT_GOALS.md`` at startup (graceful no-op if
absent), per the modules/README Agent Intelligence Layer contract.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_VIDEO_GEN_DB",
    os.path.join(os.path.dirname(__file__), "eva-video-generator.db"),
)

# Repo root = modules/video-generator -> modules -> repo
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

VALID_STATUSES = (
    "draft",
    "storyboard_ready",
    "approved",
    "rendering",
    "rendered",
    "failed",
)

# ---------------------------------------------------------------------------
# Schema + indexes + append-only triggers (trigger SQL copied from postcards)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id                       TEXT PRIMARY KEY,
    title                    TEXT NOT NULL,
    script_text              TEXT NOT NULL DEFAULT '',
    content_engine_draft_id  TEXT,
    status                   TEXT NOT NULL DEFAULT 'draft',
    scenes_json              TEXT NOT NULL DEFAULT '[]',
    output_path              TEXT NOT NULL DEFAULT '',
    error                    TEXT NOT NULL DEFAULT '',
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_ledger (
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

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);

-- The video ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS video_ledger_no_update
BEFORE UPDATE ON video_ledger
BEGIN
    SELECT RAISE(ABORT, 'video_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS video_ledger_no_delete
BEFORE DELETE ON video_ledger
BEGIN
    SELECT RAISE(ABORT, 'video_ledger is append-only');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Thin sync sqlite3 data-access layer. Opens a fresh connection per op."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    # -- connection helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- videos -------------------------------------------------------------

    def insert_video(self, data: dict) -> dict:
        ts = _now()
        row = {
            "id": data.get("id") or str(uuid.uuid4()),
            "title": data["title"],
            "script_text": data.get("script_text", ""),
            "content_engine_draft_id": data.get("content_engine_draft_id"),
            "status": data.get("status", "draft"),
            "scenes_json": json.dumps(data.get("scenes", [])),
            "output_path": data.get("output_path", ""),
            "error": data.get("error", ""),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO videos
                   (id, title, script_text, content_engine_draft_id, status,
                    scenes_json, output_path, error, created_at, updated_at)
                   VALUES (:id, :title, :script_text, :content_engine_draft_id,
                           :status, :scenes_json, :output_path, :error,
                           :created_at, :updated_at)""",
                row,
            )
        return self._hydrate(row)

    def get_video(self, video_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM videos WHERE id = ?", (video_id,)
            ).fetchone()
        return self._hydrate(dict(r)) if r else None

    def list_videos(self, status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM videos {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._hydrate(dict(r)) for r in rows]

    def update_video(self, video_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_video(video_id)
        cols = dict(fields)
        if "scenes" in cols:
            cols["scenes_json"] = json.dumps(cols.pop("scenes"))
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = video_id
        with self._connect() as conn:
            conn.execute(f"UPDATE videos SET {assignments} WHERE id = :id", cols)
        return self.get_video(video_id)

    @staticmethod
    def _hydrate(row: dict) -> dict:
        out = dict(row)
        try:
            out["scenes"] = json.loads(out.get("scenes_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            out["scenes"] = []
        return out

    # -- video ledger -------------------------------------------------------

    def append_ledger(
        self,
        event_type: str,
        entity_type: str = "",
        entity_id: str = "",
        actor: str = "",
        details: Optional[dict] = None,
    ) -> dict:
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
                """INSERT INTO video_ledger
                   (id, ts, event_type, entity_type, entity_id, actor, details_json)
                   VALUES (:id, :ts, :event_type, :entity_type, :entity_id,
                           :actor, :details_json)""",
                row,
            )
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def query_ledger(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        clauses, params = [], []
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM video_ledger {where} ORDER BY ts ASC", params
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

    def remember(self, key: str, value: str, source: str = "agent") -> dict:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source)
                   VALUES (:key, :value, :ts, :source)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value, ts = excluded.ts, source = excluded.source""",
                row,
            )
        return row

    def recall(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return r["value"] if r else None

    def all_memory(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM memory").fetchall()
        return {r["key"]: r["value"] for r in rows}


def read_mission_and_goals() -> dict:
    """Read the shared north-star docs at startup. Graceful no-op if absent."""
    out = {"mission": "", "current_goals": ""}
    for key, rel in (("mission", "docs/MISSION.md"),
                     ("current_goals", "docs/CURRENT_GOALS.md")):
        path = os.path.join(_REPO_ROOT, rel)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                out[key] = fh.read()
        except (FileNotFoundError, OSError):
            out[key] = ""
    return out
