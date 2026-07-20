"""
EVA Idea-Generator-Agent — sqlite persistence.

Two tables: ``idea_runs`` (every scored idea, append-only history) and
``digest_runs`` (every daily alignment digest). Stdlib sqlite3 only.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_IDEA_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "idea_generator.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idea_runs (
    idea_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    composite_score REAL,
    recommendation TEXT,
    acquire_candidate INTEGER,
    flags TEXT,
    sub_scores TEXT,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (idea_id, scored_at)
);

CREATE TABLE IF NOT EXISTS digest_runs (
    computed_at TEXT PRIMARY KEY,
    window_days INTEGER,
    total_events INTEGER,
    goal_track_share REAL,
    off_thesis_share REAL,
    recent_low_synergy_builds INTEGER,
    status TEXT,
    red_flags TEXT
);
"""


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_SCHEMA)
    return conn


def save_idea_result(result: dict, *, db_path: Optional[str] = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO idea_runs (idea_id, title, category, composite_score, "
            "recommendation, acquire_candidate, flags, sub_scores, scored_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result["idea_id"], result["title"], result.get("category"),
                result["composite_score"], result["recommendation"],
                int(bool(result.get("acquire_candidate"))),
                json.dumps(result.get("flags", [])),
                json.dumps(result.get("sub_scores", {})),
                result["scored_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_idea_runs(*, idea_id: Optional[str] = None, limit: Optional[int] = None,
                    db_path: Optional[str] = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        q = "SELECT * FROM idea_runs"
        params: list = []
        if idea_id:
            q += " WHERE idea_id = ?"
            params.append(idea_id)
        q += " ORDER BY scored_at DESC"
        if limit:
            q += " LIMIT ?"
            params.append(limit)
        cur = conn.execute(q, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        rec = dict(zip(cols, row))
        rec["flags"] = json.loads(rec.get("flags") or "[]")
        rec["sub_scores"] = json.loads(rec.get("sub_scores") or "{}")
        rec["acquire_candidate"] = bool(rec.get("acquire_candidate"))
        out.append(rec)
    return out


def save_digest(digest: dict, *, db_path: Optional[str] = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO digest_runs (computed_at, window_days, "
            "total_events, goal_track_share, off_thesis_share, "
            "recent_low_synergy_builds, status, red_flags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                digest["computed_at"], digest["window_days"], digest["total_events"],
                digest["goal_track_share"], digest["off_thesis_share"],
                digest["recent_low_synergy_builds"], digest["status"],
                json.dumps(digest.get("red_flags", [])),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_digests(*, limit: int = 30, db_path: Optional[str] = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        q = "SELECT * FROM digest_runs ORDER BY computed_at DESC LIMIT ?"
        cur = conn.execute(q, (limit,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        rec = dict(zip(cols, row))
        rec["red_flags"] = json.loads(rec.get("red_flags") or "[]")
        out.append(rec)
    return out


__all__ = ["DB_PATH", "save_idea_result", "list_idea_runs", "save_digest", "list_digests"]
