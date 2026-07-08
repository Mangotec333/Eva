"""
EVA LinkedIn Analytics — SQLite persistence layer (stdlib sqlite3, sync).

Follows the ``modules/projects`` / ``modules/postcards`` convention of using the
standard-library ``sqlite3`` module (no aiosqlite dependency) so the service is
fully runnable offline. The ``analytics_ledger`` table is made append-only with
BEFORE UPDATE / BEFORE DELETE triggers, exactly like projects' ``project_ledger``
and postcards' ``publish_ledger``.

Analytics snapshots are upserted on a composite uniqueness key
``(post_urn, window_start, window_end, source)`` so re-syncing the same window
does not duplicate rows — it updates the metrics in place.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from models import (
    DEFAULT_ACCESS_TOKEN_ENV,
    DEFAULT_SYNC_WINDOW_DAYS,
)

DB_PATH = os.environ.get(
    "EVA_LINKEDIN_ANALYTICS_DB",
    os.path.join(os.path.dirname(__file__), "eva-linkedin-analytics.db"),
)

# ---------------------------------------------------------------------------
# Schema (spec section 4) + indexes + append-only triggers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS linkedin_posts (
    post_urn      TEXT PRIMARY KEY,
    share_urn     TEXT NOT NULL DEFAULT '',
    author_urn    TEXT NOT NULL DEFAULT '',
    posted_at     TEXT NOT NULL DEFAULT '',
    text          TEXT NOT NULL DEFAULT '',
    post_url      TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linkedin_analytics (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    post_urn           TEXT NOT NULL REFERENCES linkedin_posts(post_urn) ON DELETE CASCADE,
    snapshot_ts        TEXT NOT NULL,
    window_start       TEXT NOT NULL DEFAULT '',
    window_end         TEXT NOT NULL DEFAULT '',
    impressions        INTEGER NOT NULL DEFAULT 0,
    unique_impressions INTEGER NOT NULL DEFAULT 0,
    clicks             INTEGER NOT NULL DEFAULT 0,
    reactions          INTEGER NOT NULL DEFAULT 0,
    comments           INTEGER NOT NULL DEFAULT 0,
    shares             INTEGER NOT NULL DEFAULT 0,
    engagement_rate    REAL NOT NULL DEFAULT 0,
    raw_json           TEXT NOT NULL DEFAULT '{}',
    source             TEXT NOT NULL DEFAULT 'stub',
    UNIQUE(post_urn, window_start, window_end, source)
);

CREATE TABLE IF NOT EXISTS linkedin_sync_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS analytics_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_analytics_post ON linkedin_analytics(post_urn);
CREATE INDEX IF NOT EXISTS idx_analytics_snapshot ON linkedin_analytics(snapshot_ts);
CREATE INDEX IF NOT EXISTS idx_posts_author ON linkedin_posts(author_urn);

-- The analytics ledger is append-only: block UPDATE and DELETE.
CREATE TRIGGER IF NOT EXISTS analytics_ledger_no_update
BEFORE UPDATE ON analytics_ledger
BEGIN
    SELECT RAISE(ABORT, 'analytics_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS analytics_ledger_no_delete
BEFORE DELETE ON analytics_ledger
BEGIN
    SELECT RAISE(ABORT, 'analytics_ledger is append-only');
END;
"""

# Defaults for the config key/value table (written once on init).
_CONFIG_DEFAULTS = {
    "author_urn": "",
    "access_token_env": DEFAULT_ACCESS_TOKEN_ENV,
    "last_sync_at": "",
    "sync_window_days": str(DEFAULT_SYNC_WINDOW_DAYS),
    "next_due": "",
}


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
            for key, value in _CONFIG_DEFAULTS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO linkedin_sync_config (key, value) "
                    "VALUES (?, ?)",
                    (key, value),
                )

    # -- posts --------------------------------------------------------------

    def upsert_post(self, data: dict) -> dict:
        """Insert a post or update its mutable fields, preserving first_seen_at."""
        ts = _now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM linkedin_posts WHERE post_urn = ?",
                (data["post_urn"],),
            ).fetchone()
            first_seen = existing["first_seen_at"] if existing else ts
            row = {
                "post_urn": data["post_urn"],
                "share_urn": data.get("share_urn", "") or "",
                "author_urn": data.get("author_urn", "") or "",
                "posted_at": data.get("posted_at", "") or "",
                "text": data.get("text", "") or "",
                "post_url": data.get("post_url", "") or "",
                "first_seen_at": first_seen,
                "updated_at": ts,
            }
            conn.execute(
                """INSERT INTO linkedin_posts
                   (post_urn, share_urn, author_urn, posted_at, text, post_url,
                    first_seen_at, updated_at)
                   VALUES (:post_urn, :share_urn, :author_urn, :posted_at, :text,
                           :post_url, :first_seen_at, :updated_at)
                   ON CONFLICT(post_urn) DO UPDATE SET
                       share_urn=excluded.share_urn,
                       author_urn=excluded.author_urn,
                       posted_at=excluded.posted_at,
                       text=excluded.text,
                       post_url=excluded.post_url,
                       updated_at=excluded.updated_at""",
                row,
            )
        return row

    def get_post(self, post_urn: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM linkedin_posts WHERE post_urn = ?", (post_urn,)
            ).fetchone()
        return dict(r) if r else None

    def list_posts(self) -> List[dict]:
        """List posts with their latest snapshot's key metrics joined in."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT p.*,
                       a.snapshot_ts     AS latest_snapshot_ts,
                       a.impressions     AS impressions,
                       a.clicks          AS clicks,
                       a.reactions       AS reactions,
                       a.comments        AS comments,
                       a.shares          AS shares,
                       a.engagement_rate AS engagement_rate,
                       a.source          AS source
                FROM linkedin_posts p
                LEFT JOIN linkedin_analytics a
                    ON a.id = (
                        SELECT id FROM linkedin_analytics
                        WHERE post_urn = p.post_urn
                        ORDER BY snapshot_ts DESC, id DESC LIMIT 1
                    )
                ORDER BY COALESCE(a.impressions, 0) DESC, p.posted_at DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def count_posts(self) -> int:
        with self._connect() as conn:
            r = conn.execute("SELECT COUNT(*) AS c FROM linkedin_posts").fetchone()
        return int(r["c"])

    # -- analytics snapshots ------------------------------------------------

    def upsert_snapshot(self, data: dict) -> dict:
        """Upsert a snapshot on (post_urn, window_start, window_end, source).

        Returns a dict with an extra ``_inserted`` flag: True if a new row was
        created, False if an existing row was updated. This lets the service
        report idempotency accurately.
        """
        ts = data.get("snapshot_ts") or _now()
        row = {
            "post_urn": data["post_urn"],
            "snapshot_ts": ts,
            "window_start": data.get("window_start", "") or "",
            "window_end": data.get("window_end", "") or "",
            "impressions": int(data.get("impressions", 0) or 0),
            "unique_impressions": int(data.get("unique_impressions", 0) or 0),
            "clicks": int(data.get("clicks", 0) or 0),
            "reactions": int(data.get("reactions", 0) or 0),
            "comments": int(data.get("comments", 0) or 0),
            "shares": int(data.get("shares", 0) or 0),
            "engagement_rate": float(data.get("engagement_rate", 0.0) or 0.0),
            "raw_json": data.get("raw_json", "{}") or "{}",
            "source": data.get("source", "stub") or "stub",
        }
        with self._connect() as conn:
            existing = conn.execute(
                """SELECT id FROM linkedin_analytics
                   WHERE post_urn = ? AND window_start = ? AND window_end = ?
                     AND source = ?""",
                (row["post_urn"], row["window_start"], row["window_end"],
                 row["source"]),
            ).fetchone()
            inserted = existing is None
            conn.execute(
                """INSERT INTO linkedin_analytics
                   (post_urn, snapshot_ts, window_start, window_end, impressions,
                    unique_impressions, clicks, reactions, comments, shares,
                    engagement_rate, raw_json, source)
                   VALUES (:post_urn, :snapshot_ts, :window_start, :window_end,
                           :impressions, :unique_impressions, :clicks, :reactions,
                           :comments, :shares, :engagement_rate, :raw_json, :source)
                   ON CONFLICT(post_urn, window_start, window_end, source)
                   DO UPDATE SET
                       snapshot_ts=excluded.snapshot_ts,
                       impressions=excluded.impressions,
                       unique_impressions=excluded.unique_impressions,
                       clicks=excluded.clicks,
                       reactions=excluded.reactions,
                       comments=excluded.comments,
                       shares=excluded.shares,
                       engagement_rate=excluded.engagement_rate,
                       raw_json=excluded.raw_json""",
                row,
            )
        out = dict(row)
        out["_inserted"] = inserted
        return out

    def list_snapshots(self, post_urn: str) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM linkedin_analytics WHERE post_urn = ? "
                "ORDER BY snapshot_ts ASC, id ASC",
                (post_urn,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_snapshots(self) -> int:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM linkedin_analytics"
            ).fetchone()
        return int(r["c"])

    def top_post_by_impressions(self, since_ts: Optional[str] = None) -> Optional[dict]:
        """Post with the highest impressions in its latest snapshot.

        ``since_ts`` filters to posts whose latest snapshot is at or after the
        timestamp (used for the last-N-days summary).
        """
        posts = self.list_posts()
        best: Optional[dict] = None
        for p in posts:
            if p.get("impressions") is None:
                continue
            if since_ts and (p.get("latest_snapshot_ts") or "") < since_ts:
                continue
            if best is None or (p["impressions"] or 0) > (best["impressions"] or 0):
                best = p
        return best

    # -- sync config --------------------------------------------------------

    def get_config(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM linkedin_sync_config"
            ).fetchall()
        cfg = {r["key"]: r["value"] for r in rows}
        # Coerce the int field for convenience.
        try:
            cfg["sync_window_days"] = int(cfg.get("sync_window_days") or
                                          DEFAULT_SYNC_WINDOW_DAYS)
        except (TypeError, ValueError):
            cfg["sync_window_days"] = DEFAULT_SYNC_WINDOW_DAYS
        return cfg

    def set_config(self, fields: dict) -> dict:
        with self._connect() as conn:
            for key, value in fields.items():
                conn.execute(
                    "INSERT INTO linkedin_sync_config (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, "" if value is None else str(value)),
                )
        return self.get_config()

    # -- ledger -------------------------------------------------------------

    def append_ledger(
        self,
        event_type: str,
        entity_type: str = "",
        entity_id: str = "",
        actor: str = "",
        details: Optional[dict] = None,
    ) -> dict:
        row = {
            "ts": _now(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor": actor,
            "details_json": json.dumps(details or {}, default=str),
        }
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO analytics_ledger
                   (ts, event_type, entity_type, entity_id, actor, details_json)
                   VALUES (:ts, :event_type, :entity_type, :entity_id, :actor,
                           :details_json)""",
                row,
            )
            row_id = cur.lastrowid
        out = dict(row)
        out["id"] = row_id
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def query_ledger(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[dict]:
        clauses, params = [], []
        if from_ts:
            clauses.append("ts >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("ts <= ?")
            params.append(to_ts)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM analytics_ledger {where} ORDER BY ts ASC, id ASC",
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

    # -- memory (agent intelligence layer) ----------------------------------

    def memory_set(self, key: str, value: str, source: str = "system") -> dict:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory (key, value, ts, source) "
                "VALUES (:key, :value, :ts, :source) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "ts=excluded.ts, source=excluded.source",
                row,
            )
        return row

    def memory_get(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return dict(r) if r else None

    def memory_all(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory ORDER BY key ASC"
            ).fetchall()
        return [dict(r) for r in rows]
