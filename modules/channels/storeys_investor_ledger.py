"""
EVA Channels — Storeys investor dedup ledger ("don't ask again").

Separate SQLite ledger from ``enrolled_contacts.py`` (which is the Eva
Acquisition PE/M&A ledger). Storeys investor-outreach dedup must not share
state with Eva Acquisition — an email already enrolled into the 7-touch PE/
M&A sequence is a different pipeline/purpose and should still be eligible for
Storeys investor outreach, and vice versa.

SQLite only (no Postgres path) — this is a new, low-volume ledger; add a PG
backend later if/when Storeys sourcing volume justifies it.

Emails are always lower-cased so dedup is case-insensitive.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "STOREYS_INVESTOR_LEDGER_DB",
    os.path.join(os.path.dirname(__file__), "storeys_investor_enrolled.db"),
)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storeys_investor_enrolled (
                email          TEXT PRIMARY KEY,
                source         TEXT DEFAULT '',
                ghl_contact_id TEXT DEFAULT '',
                enrolled_at    TEXT NOT NULL
            )
            """
        )
        conn.commit()


def is_enrolled(email: str) -> bool:
    key = _norm(email)
    if not key:
        return False
    _init()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM storeys_investor_enrolled WHERE email = ?", (key,)
        ).fetchone()
    return row is not None


def mark_enrolled(email: str, source: str = "", ghl_contact_id: str = "") -> dict:
    key = _norm(email)
    if not key:
        return {"ok": False, "error": "empty email"}
    _init()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO storeys_investor_enrolled (email, source, ghl_contact_id, enrolled_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                source = excluded.source,
                ghl_contact_id = excluded.ghl_contact_id
            """,
            (key, source, ghl_contact_id, now),
        )
        conn.commit()
    return {"ok": True, "email": key, "source": source, "ghl_contact_id": ghl_contact_id}


def count() -> int:
    _init()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM storeys_investor_enrolled").fetchone()
    return int(row["n"]) if row else 0


__all__ = ["is_enrolled", "mark_enrolled", "count"]
