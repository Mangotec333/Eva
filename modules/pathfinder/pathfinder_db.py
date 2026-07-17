"""
EVA Pathfinder — SQLite Database Layer
DB path: ~/.eva/pathfinder.db
Table: leads
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
EVA_DIR = Path.home() / ".eva"
EVA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = EVA_DIR / "pathfinder.db"

# ── Stages ────────────────────────────────────────────────────────────────────
STAGES = ["new", "contacted", "replied", "meeting_booked", "closed", "archived"]

# ── Canonical per-agent memory + append-only ledger (Architecture Directive) ────
# Schema + immutability triggers copied verbatim from the reference modules
# (modules/postcards, modules/meet-ingest).
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


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the leads table if it doesn't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                email       TEXT NOT NULL UNIQUE,
                company     TEXT,
                tier        TEXT,
                usecase     TEXT,
                score       INTEGER DEFAULT 0,
                sequence    TEXT,
                stage       TEXT DEFAULT 'new',
                created_at  TEXT NOT NULL,
                last_contact TEXT,
                notes       TEXT
            )
        """)
        conn.executescript(_MEM_LEDGER_SCHEMA)
        conn.commit()


def insert_lead(
    name: str,
    email: str,
    company: Optional[str],
    tier: str,
    usecase: Optional[str],
    score: int,
    sequence: str,
) -> int:
    """Insert a new lead. Returns the new row id."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO leads (name, email, company, tier, usecase, score, sequence, stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (name, email, company, tier, usecase, score, sequence, now),
        )
        conn.commit()
        return cur.lastrowid


def get_all_leads() -> list[dict]:
    """Return all leads as a list of dicts, ordered by score desc."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY score DESC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_lead_by_id(lead_id: int) -> Optional[dict]:
    """Return a single lead by id, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        return dict(row) if row else None


def advance_lead_stage(lead_id: int) -> Optional[dict]:
    """
    Move a lead to the next stage in the pipeline.
    Updates last_contact to now.
    Returns the updated lead dict, or None if not found / already terminal.
    """
    lead = get_lead_by_id(lead_id)
    if lead is None:
        return None

    current_stage = lead["stage"]
    if current_stage not in STAGES:
        return None

    current_idx = STAGES.index(current_stage)
    if current_idx >= len(STAGES) - 1:
        # Already at final stage (archived) — no-op
        return lead

    next_stage = STAGES[current_idx + 1]
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET stage = ?, last_contact = ? WHERE id = ?",
            (next_stage, now, lead_id),
        )
        conn.commit()

    return get_lead_by_id(lead_id)


def update_lead_notes(lead_id: int, notes: str) -> Optional[dict]:
    """Append or overwrite notes on a lead."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET notes = ? WHERE id = ?",
            (notes, lead_id),
        )
        conn.commit()
    return get_lead_by_id(lead_id)


def get_follow_up_today() -> list[dict]:
    """
    Return leads that are in 'new' or 'contacted' stage and have
    not been contacted today — surface as 'follow up today' candidates.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM leads
            WHERE stage IN ('new', 'contacted')
              AND (last_contact IS NULL OR last_contact < ?)
            ORDER BY score DESC
            """,
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── memory (per-agent knowledge) + append-only ledger accessors ─────────────────

def set_memory(key: str, value: str, source: str = "system") -> dict:
    init_db()
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, ts=excluded.ts, source=excluded.source""",
            (key, value, now, source),
        )
        conn.commit()
    return {"key": key, "value": value, "ts": now, "source": source}


def get_memory(key: str, default: Optional[str] = None) -> Optional[str]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def list_memory() -> list[dict]:
    init_db()
    with get_connection() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM memory ORDER BY key").fetchall()]


def append_ledger(event_type: str, entity_type: str = "", entity_id: str = "",
                  actor: str = "", details: Optional[dict] = None) -> dict:
    init_db()
    row = {
        "id": str(uuid.uuid4()), "ts": _now(), "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id, "actor": actor,
        "details_json": json.dumps(details or {}),
    }
    with get_connection() as conn:
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


def query_ledger(event_type: Optional[str] = None) -> list[dict]:
    init_db()
    q, params = "SELECT * FROM ledger", []
    if event_type:
        q += " WHERE event_type=?"
        params.append(event_type)
    q += " ORDER BY ts ASC"
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
    return rows


# ── Init on import ─────────────────────────────────────────────────────────────
init_db()
