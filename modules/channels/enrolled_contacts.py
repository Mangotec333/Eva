"""
EVA Channels — enrolled-contacts dedup ledger ("don't ask again").

The canonical store is Postgres table ``enrolled_contacts`` (see
``infra/init/postgres/02_enrolled_contacts.sql``). Before the Apollo→GHL
pipeline adds any contact it calls :func:`is_enrolled`; a hit means the contact
has already been put through outreach and is skipped. On a successful enrol the
pipeline calls :func:`mark_enrolled`.

Backend selection is automatic and fails safe:

* **Postgres** when ``psycopg2`` imports and a connection succeeds (via
  ``infra.db_client.pg`` when importable, else env-configured ``psycopg2``).
* **SQLite fallback** otherwise — used by the offline test suite and the
  launcher's minimal env. Path from ``ENROLLED_CONTACTS_DB`` (defaults beside
  this module). Set ``EVA_ENROLLED_OFFLINE=1`` to force the fallback.

Emails are always lower-cased so dedup is case-insensitive.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_SQLITE_PATH = os.environ.get(
    "ENROLLED_CONTACTS_DB",
    os.path.join(os.path.dirname(__file__), "enrolled_contacts.db"),
)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _force_offline() -> bool:
    return os.environ.get("EVA_ENROLLED_OFFLINE") == "1"


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------

def _pg_conn():
    """Return a live Postgres connection, or None if unavailable."""
    if _force_offline():
        return None
    try:
        import psycopg2  # noqa: PLC0415
    except Exception:
        return None
    # Prefer the repo's shared client so host/db/creds stay in one place.
    try:
        import sys
        infra = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "infra"))
        if infra not in sys.path:
            sys.path.insert(0, infra)
        from db_client import pg  # type: ignore  # noqa: PLC0415
        return pg()
    except Exception:
        pass
    try:
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "eva"),
            user=os.getenv("POSTGRES_USER", "eva"),
            password=os.getenv("POSTGRES_PASSWORD", "eva_local_secret"),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SQLite fallback
# ---------------------------------------------------------------------------

def _sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS enrolled_contacts (
            email           TEXT UNIQUE,
            source          TEXT,
            ghl_contact_id  TEXT,
            enrolled_at     TEXT DEFAULT ''
        )
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Public API — backend-agnostic
# ---------------------------------------------------------------------------

def is_enrolled(email: str) -> bool:
    """True if ``email`` is already in the enrolled ledger."""
    key = _norm(email)
    if not key:
        return False
    conn = _pg_conn()
    if conn is not None:
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM enrolled_contacts WHERE email=%s", (key,))
                return cur.fetchone() is not None
        except Exception:
            pass  # fall through to sqlite
        finally:
            _safe_close(conn)
    with _sqlite_conn() as sconn:
        cur = sconn.execute("SELECT 1 FROM enrolled_contacts WHERE email=?", (key,))
        return cur.fetchone() is not None


def mark_enrolled(email: str, source: str = "", ghl_contact_id: str = "") -> dict:
    """Record ``email`` as enrolled. Idempotent (UNIQUE email upsert)."""
    key = _norm(email)
    if not key:
        return {"ok": False, "error": "empty email"}
    now = datetime.now(timezone.utc).isoformat()
    conn = _pg_conn()
    if conn is not None:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO enrolled_contacts (email, source, ghl_contact_id, enrolled_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (email) DO UPDATE
                        SET source = EXCLUDED.source,
                            ghl_contact_id = EXCLUDED.ghl_contact_id
                    """,
                    (key, source, ghl_contact_id),
                )
            return {"ok": True, "email": key, "backend": "postgres"}
        except Exception as exc:
            last = f"postgres write failed: {exc}"
        finally:
            _safe_close(conn)
    else:
        last = ""
    try:
        with _sqlite_conn() as sconn:
            sconn.execute(
                """
                INSERT INTO enrolled_contacts (email, source, ghl_contact_id, enrolled_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE
                    SET source=excluded.source, ghl_contact_id=excluded.ghl_contact_id
                """,
                (key, source, ghl_contact_id, now),
            )
        return {"ok": True, "email": key, "backend": "sqlite"}
    except Exception as exc:
        return {"ok": False, "email": key, "error": f"{last} sqlite write failed: {exc}".strip()}


def count() -> int:
    conn = _pg_conn()
    if conn is not None:
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM enrolled_contacts")
                return int(cur.fetchone()[0])
        except Exception:
            pass
        finally:
            _safe_close(conn)
    with _sqlite_conn() as sconn:
        cur = sconn.execute("SELECT COUNT(*) FROM enrolled_contacts")
        return int(cur.fetchone()[0])


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


__all__ = ["is_enrolled", "mark_enrolled", "count"]
