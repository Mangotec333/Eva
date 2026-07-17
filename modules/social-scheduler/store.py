"""
EVA Social-Scheduler — the one local SQLite store (Eva owns the data).

Everything the daily LinkedIn + X publisher needs lives here, in a single
sqlite file inside the Eva data directory — NO third-party data store, NO
Postiz, NO SaaS DB. Three tables:

  * ``content_queue``    — the rolling content queue (day-1 pre-seed + future
    days drafted by content-engine). One row per (post × day). A stable
    ``headline_hash`` is UNIQUE so a headline is never queued twice
    (dedupe by headline hash, per the spec's 30-day rolling rule).
  * ``post_history``     — one row per *published* post, with the platform IDs
    (LinkedIn UGC urn + X tweet id) and the CTA-comment IDs so analytics and
    audits can always resolve what went out.
  * ``analytics``        — the unified engagement store. One row per
    (platform, post_id, retrieved_at) snapshot: impressions, likes, comments,
    clicks. LinkedIn metrics come from modules/linkedin-analytics; X metrics
    from the X API v2 client in analytics.py.

The DB lives beside this module by default (gitignored, *.db) and is overridable
with ``SOCIAL_SCHEDULER_DB`` so the launchd service can point it at the Eva data
directory. Stdlib only (sqlite3).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "SOCIAL_SCHEDULER_DB",
    os.path.join(os.path.dirname(__file__), "social_scheduler.db"),
)

# Queue-item lifecycle.
STATUS_QUEUED = "queued"          # waiting for its ET slot
STATUS_SUBMITTED = "submitted"    # posted to the social-publish Slack gate
STATUS_PUBLISHED = "published"    # approved + published to LI/X, CTA done
STATUS_FAILED = "failed"          # publish failed on every platform
STATUS_SKIPPED = "skipped"        # manually skipped


# ---------------------------------------------------------------------------
# Canonical per-agent memory + append-only ledger (Architecture Directive).
# Schema + immutability triggers copied verbatim from the reference modules
# (modules/postcards, modules/meet-ingest).
# ---------------------------------------------------------------------------

_MEM_LEDGER_SCHEMA = """
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def headline_hash(headline: str) -> str:
    """Stable dedupe key for a headline (never repeat a posted headline)."""
    raw = (headline or "").strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto dedupe key


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_queue (
                id             TEXT PRIMARY KEY,
                headline       TEXT NOT NULL,
                headline_hash  TEXT NOT NULL UNIQUE,
                text           TEXT NOT NULL,
                image_path     TEXT NOT NULL DEFAULT '',
                platforms      TEXT NOT NULL DEFAULT '["linkedin","x"]',
                cta            TEXT NOT NULL DEFAULT '',
                scheduled_date TEXT NOT NULL,
                slot           TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'queued',
                draft_id       TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS post_history (
                id             TEXT PRIMARY KEY,
                queue_id       TEXT NOT NULL DEFAULT '',
                headline       TEXT NOT NULL DEFAULT '',
                li_post_id     TEXT NOT NULL DEFAULT '',
                x_tweet_id     TEXT NOT NULL DEFAULT '',
                li_comment_id  TEXT NOT NULL DEFAULT '',
                x_reply_id     TEXT NOT NULL DEFAULT '',
                li_liked       INTEGER NOT NULL DEFAULT 0,
                x_liked        INTEGER NOT NULL DEFAULT 0,
                results        TEXT NOT NULL DEFAULT '{}',
                published_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics (
                id            TEXT PRIMARY KEY,
                platform      TEXT NOT NULL,
                post_id       TEXT NOT NULL,
                impressions   INTEGER NOT NULL DEFAULT 0,
                likes         INTEGER NOT NULL DEFAULT 0,
                comments      INTEGER NOT NULL DEFAULT 0,
                clicks        INTEGER NOT NULL DEFAULT 0,
                retrieved_at  TEXT NOT NULL,
                UNIQUE(platform, post_id, retrieved_at)
            )
            """
        )
        conn.executescript(_MEM_LEDGER_SCHEMA)
        conn.commit()


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def _queue_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["platforms"] = json.loads(d.get("platforms") or "[]")
    return d


# ---------------------------------------------------------------------------
# content_queue
# ---------------------------------------------------------------------------

def enqueue(*, headline: str, text: str, image_path: str = "",
            platforms: list[str] | None = None, cta: str = "",
            scheduled_date: str, slot: str,
            path: str | None = None) -> dict:
    """Insert a queue item, deduped by headline hash.

    Re-queuing a headline already in the queue is a no-op that returns the
    existing row with ``duplicate=True`` (never repeat a posted headline).
    """
    init_db(path)
    h = headline_hash(headline)
    now = _now()
    platforms = platforms or ["linkedin", "x"]
    with _connect(path) as conn:
        existing = conn.execute(
            "SELECT * FROM content_queue WHERE headline_hash=?", (h,)
        ).fetchone()
        if existing is not None:
            d = _queue_row(existing)
            d["duplicate"] = True
            return d
        qid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO content_queue
               (id, headline, headline_hash, text, image_path, platforms, cta,
                scheduled_date, slot, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (qid, headline, h, text, image_path or "", json.dumps(platforms),
             cta, scheduled_date, slot, STATUS_QUEUED, now, now),
        )
        conn.commit()
        d = _queue_row(conn.execute(
            "SELECT * FROM content_queue WHERE id=?", (qid,)).fetchone())
        d["duplicate"] = False
        return d


def get_queue_item(qid: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM content_queue WHERE id=?", (qid,)).fetchone()
        return _queue_row(row) if row else None


def list_queue(status: str | None = None, path: str | None = None) -> list[dict]:
    """Queue items ordered by their scheduled ET slot (soonest first)."""
    init_db(path)
    with _connect(path) as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM content_queue WHERE status=? "
                "ORDER BY scheduled_date, slot", (status,))
        else:
            cur = conn.execute(
                "SELECT * FROM content_queue ORDER BY scheduled_date, slot")
        return [_queue_row(r) for r in cur.fetchall()]


def update_queue_item(qid: str, fields: dict, path: str | None = None) -> dict | None:
    if not fields:
        return get_queue_item(qid, path)
    init_db(path)
    clean = dict(fields)
    if "platforms" in clean and not isinstance(clean["platforms"], str):
        clean["platforms"] = json.dumps(clean["platforms"])
    clean["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in clean)
    params = list(clean.values()) + [qid]
    with _connect(path) as conn:
        conn.execute(f"UPDATE content_queue SET {cols} WHERE id=?", params)
        conn.commit()
    return get_queue_item(qid, path)


def prune_queue(before_date: str, path: str | None = None) -> int:
    """Drop still-queued items scheduled before ``before_date`` (30-day roll).

    Published/failed history is preserved in ``post_history``; this only trims
    stale *unposted* queue rows so the rolling window stays bounded.
    """
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute(
            "DELETE FROM content_queue WHERE status=? AND scheduled_date < ?",
            (STATUS_QUEUED, before_date))
        conn.commit()
        return cur.rowcount


# ---------------------------------------------------------------------------
# post_history
# ---------------------------------------------------------------------------

def record_post(*, queue_id: str = "", headline: str = "",
                li_post_id: str = "", x_tweet_id: str = "",
                li_comment_id: str = "", x_reply_id: str = "",
                li_liked: bool = False, x_liked: bool = False,
                results: dict | None = None,
                path: str | None = None) -> dict:
    init_db(path)
    pid = str(uuid.uuid4())
    now = _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO post_history
               (id, queue_id, headline, li_post_id, x_tweet_id, li_comment_id,
                x_reply_id, li_liked, x_liked, results, published_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, queue_id, headline, li_post_id, x_tweet_id, li_comment_id,
             x_reply_id, int(li_liked), int(x_liked),
             json.dumps(results or {}), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM post_history WHERE id=?", (pid,)).fetchone()
        d = _row(row)
        d["results"] = json.loads(d.get("results") or "{}")
        return d


def list_posts(path: str | None = None) -> list[dict]:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute("SELECT * FROM post_history ORDER BY published_at DESC")
        out = []
        for r in cur.fetchall():
            d = _row(r)
            d["results"] = json.loads(d.get("results") or "{}")
            out.append(d)
        return out


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------

def record_metric(*, platform: str, post_id: str, impressions: int = 0,
                  likes: int = 0, comments: int = 0, clicks: int = 0,
                  retrieved_at: str | None = None,
                  path: str | None = None) -> dict:
    """Upsert one engagement snapshot (idempotent per retrieved_at minute)."""
    init_db(path)
    ts = retrieved_at or _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO analytics
               (id, platform, post_id, impressions, likes, comments, clicks,
                retrieved_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(platform, post_id, retrieved_at) DO UPDATE SET
                 impressions=excluded.impressions,
                 likes=excluded.likes,
                 comments=excluded.comments,
                 clicks=excluded.clicks""",
            (str(uuid.uuid4()), platform, post_id, int(impressions),
             int(likes), int(comments), int(clicks), ts),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM analytics WHERE platform=? AND post_id=? AND retrieved_at=?",
            (platform, post_id, ts)).fetchone()
        return _row(row)


def list_metrics(platform: str | None = None, post_id: str | None = None,
                 path: str | None = None) -> list[dict]:
    init_db(path)
    clauses, params = [], []
    if platform:
        clauses.append("platform=?")
        params.append(platform)
    if post_id:
        clauses.append("post_id=?")
        params.append(post_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(path) as conn:
        cur = conn.execute(
            f"SELECT * FROM analytics {where} ORDER BY retrieved_at DESC", params)
        return [_row(r) for r in cur.fetchall()]


def latest_metrics(path: str | None = None) -> list[dict]:
    """Most-recent snapshot per (platform, post_id)."""
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute(
            """SELECT a.* FROM analytics a
               JOIN (SELECT platform, post_id, MAX(retrieved_at) AS mx
                     FROM analytics GROUP BY platform, post_id) m
               ON a.platform=m.platform AND a.post_id=m.post_id
                  AND a.retrieved_at=m.mx
               ORDER BY a.platform, a.post_id""")
        return [_row(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# memory (per-agent knowledge) + append-only ledger accessors
# ---------------------------------------------------------------------------

def set_memory(key: str, value: str, source: str = "system",
               path: str | None = None) -> dict:
    init_db(path)
    now = _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, ts=excluded.ts, source=excluded.source""",
            (key, value, now, source),
        )
        conn.commit()
    return {"key": key, "value": value, "ts": now, "source": source}


def get_memory(key: str, default: str | None = None,
               path: str | None = None) -> str | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def list_memory(path: str | None = None) -> list[dict]:
    init_db(path)
    with _connect(path) as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM memory ORDER BY key").fetchall()]


def append_ledger(event_type: str, entity_type: str = "", entity_id: str = "",
                  actor: str = "", details: dict | None = None,
                  path: str | None = None) -> dict:
    init_db(path)
    row = {
        "id": str(uuid.uuid4()), "ts": _now(), "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id, "actor": actor,
        "details_json": json.dumps(details or {}),
    }
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO ledger
               (id, ts, event_type, entity_type, entity_id, actor, details_json)
               VALUES (:id,:ts,:event_type,:entity_type,:entity_id,:actor,:details_json)""",
            row,
        )
        conn.commit()
    out = dict(row)
    out["details"] = json.loads(out.pop("details_json"))
    return out


def query_ledger(event_type: str | None = None,
                 path: str | None = None) -> list[dict]:
    init_db(path)
    q, params = "SELECT * FROM ledger", []
    if event_type:
        q += " WHERE event_type=?"
        params.append(event_type)
    q += " ORDER BY ts ASC"
    with _connect(path) as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
    return rows


__all__ = [
    "DB_PATH", "init_db", "headline_hash",
    "STATUS_QUEUED", "STATUS_SUBMITTED", "STATUS_PUBLISHED",
    "STATUS_FAILED", "STATUS_SKIPPED",
    "enqueue", "get_queue_item", "list_queue", "update_queue_item", "prune_queue",
    "record_post", "list_posts",
    "record_metric", "list_metrics", "latest_metrics",
    "set_memory", "get_memory", "list_memory",
    "append_ledger", "query_ledger",
]
