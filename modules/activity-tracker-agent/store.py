"""
EVA Activity-Tracker-Agent — sqlite persistence.

One table: ``digest_runs`` (one row per day's digest, upserted by date so
re-running a date overwrites rather than duplicates). Stdlib sqlite3 only.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_ACTIVITY_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "activity_tracker.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_runs (
    date TEXT PRIMARY KEY,
    computed_at TEXT NOT NULL,
    total_events INTEGER,
    goal_track_share REAL,
    status TEXT,
    high_leverage_projects TEXT,
    low_leverage_projects TEXT,
    double_down_recommendation TEXT,
    course_correction_notes TEXT,
    buckets TEXT,
    patterns TEXT,
    revenue_signals TEXT
);
"""


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_SCHEMA)
    return conn


def save_digest(digest: dict, *, db_path: Optional[str] = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO digest_runs (date, computed_at, total_events, "
            "goal_track_share, status, high_leverage_projects, low_leverage_projects, "
            "double_down_recommendation, course_correction_notes, buckets, patterns, "
            "revenue_signals) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                digest["date"], digest["computed_at"], digest["total_events"],
                digest["goal_track_share"], digest["status"],
                json.dumps(digest.get("high_leverage_projects", [])),
                json.dumps(digest.get("low_leverage_projects", [])),
                digest.get("double_down_recommendation"),
                json.dumps(digest.get("course_correction_notes", [])),
                json.dumps(digest.get("buckets", [])),
                json.dumps(digest.get("patterns", [])),
                json.dumps(digest.get("revenue_signals", [])),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _hydrate(rec: dict) -> dict:
    for key in ("high_leverage_projects", "low_leverage_projects",
                "course_correction_notes", "buckets", "patterns", "revenue_signals"):
        rec[key] = json.loads(rec.get(key) or "[]")
    return rec


def get_digest(date: str, *, db_path: Optional[str] = None) -> Optional[dict]:
    conn = _connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM digest_runs WHERE date = ?", (date,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return _hydrate(dict(zip(cols, row)))


def list_digests(*, limit: int = 30, db_path: Optional[str] = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM digest_runs ORDER BY date DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return [_hydrate(dict(zip(cols, row))) for row in rows]


__all__ = ["DB_PATH", "save_digest", "get_digest", "list_digests"]
