"""
EVA Treasurer — SQLite persistence for spend events + budget caps.

Two tables, both survive launcher/cron restarts:

  * ``spend_events`` — one row per logged spend. A stable ``signature``
    (category + amount + vendor + source_agent + timestamp + note) is UNIQUE so
    a cron-driven or retried ``track`` never double-counts the same spend
    (idempotent, like the social-publish / diracatron stores). Callers may also
    pass an explicit ``event_key`` to control dedup precisely.
  * ``budgets`` — one row per category holding its cap (in cents) for a period
    (day/week/month). Upserting a cap replaces it in place.

The DB lives beside this module and is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "TREASURER_DB",
    os.path.join(os.path.dirname(__file__), "treasurer.db"),
)

# ---------------------------------------------------------------------------
# Canonical per-agent memory + append-only ledger (Architecture Directive).
# Schema + immutability triggers copied verbatim from the reference modules
# (modules/postcards, modules/meet-ingest). ``memory`` = what the agent knows;
# ``ledger`` = an immutable audit trail of every state change.
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


def signature(category: str, amount_cents: int, vendor: str,
              source_agent: str, timestamp: str, note: str) -> str:
    """Stable idempotency key for a spend event."""
    raw = f"{category}|{amount_cents}|{vendor}|{source_agent}|{timestamp}|{note}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto dedup key


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spend_events (
                id            TEXT PRIMARY KEY,
                signature     TEXT NOT NULL UNIQUE,
                category      TEXT NOT NULL,
                amount_cents  INTEGER NOT NULL DEFAULT 0,
                vendor        TEXT NOT NULL DEFAULT '',
                source_agent  TEXT NOT NULL DEFAULT '',
                note          TEXT NOT NULL DEFAULT '',
                timestamp     TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category      TEXT PRIMARY KEY,
                cap_cents     INTEGER NOT NULL DEFAULT 0,
                period        TEXT NOT NULL DEFAULT 'month',
                updated_at    TEXT NOT NULL
            )
            """
        )
        conn.executescript(_MEM_LEDGER_SCHEMA)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# spend_events
# ---------------------------------------------------------------------------

def add_event(*, category: str, amount_cents: int, vendor: str = "",
              source_agent: str = "", note: str = "",
              timestamp: str | None = None, event_key: str | None = None,
              path: str | None = None) -> dict:
    """Insert a spend event, idempotently.

    If an ``event_key`` is given it *is* the dedup key; otherwise the key is
    derived from the event's content. Re-inserting the same key is a no-op that
    returns the already-stored row (so retries / cron re-runs never
    double-count), with ``duplicate=True`` attached.
    """
    init_db(path)
    ts = timestamp or _now()
    sig = event_key or signature(category, amount_cents, vendor, source_agent, ts, note)
    now = _now()
    with _connect(path) as conn:
        existing = conn.execute(
            "SELECT * FROM spend_events WHERE signature=?", (sig,)
        ).fetchone()
        if existing is not None:
            d = _row_to_dict(existing)
            d["duplicate"] = True
            return d
        eid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO spend_events
               (id, signature, category, amount_cents, vendor, source_agent,
                note, timestamp, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (eid, sig, category, int(amount_cents), vendor, source_agent,
             note, ts, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM spend_events WHERE id=?", (eid,)).fetchone()
        d = _row_to_dict(row)
        d["duplicate"] = False
        return d


def list_events(*, since: str | None = None, category: str | None = None,
                path: str | None = None) -> list[dict]:
    """All events (optionally on/after ``since`` ISO ts, optionally one category),
    newest first."""
    init_db(path)
    clauses, params = [], []
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(path) as conn:
        cur = conn.execute(
            f"SELECT * FROM spend_events {where} ORDER BY timestamp DESC", params
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def category_total(category: str, since: str | None = None,
                   path: str | None = None) -> int:
    """Sum of amount_cents for one category (optionally on/after ``since``)."""
    init_db(path)
    params: list = [category]
    q = "SELECT COALESCE(SUM(amount_cents),0) AS t FROM spend_events WHERE category=?"
    if since:
        q += " AND timestamp >= ?"
        params.append(since)
    with _connect(path) as conn:
        return int(conn.execute(q, params).fetchone()["t"])


# ---------------------------------------------------------------------------
# budgets
# ---------------------------------------------------------------------------

def set_budget(*, category: str, cap_cents: int, period: str = "month",
               path: str | None = None) -> dict:
    """Set or replace a category's budget cap in place."""
    init_db(path)
    now = _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO budgets (category, cap_cents, period, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(category) DO UPDATE SET
                 cap_cents=excluded.cap_cents,
                 period=excluded.period,
                 updated_at=excluded.updated_at""",
            (category, int(cap_cents), period, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budgets WHERE category=?", (category,)).fetchone()
        return _row_to_dict(row)


def get_budget(category: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM budgets WHERE category=?", (category,)).fetchone()
        return _row_to_dict(row) if row else None


def list_budgets(path: str | None = None) -> list[dict]:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute("SELECT * FROM budgets ORDER BY category")
        return [_row_to_dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# memory (per-agent knowledge) + append-only ledger accessors
# ---------------------------------------------------------------------------

def set_memory(key: str, value: str, source: str = "system",
               path: str | None = None) -> dict:
    """Upsert a memory record (what the agent knows)."""
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
    """Append an immutable event to the ledger (audit trail / recovery source)."""
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
    "DB_PATH", "init_db", "signature",
    "add_event", "list_events", "category_total",
    "set_budget", "get_budget", "list_budgets",
    "set_memory", "get_memory", "list_memory",
    "append_ledger", "query_ledger",
]
