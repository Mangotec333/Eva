"""
EVA Trend Agent — Competitor Scan raw-data store
==================================================

# STUB: This is a deliberate backlog placeholder, not a finished capability.
#
# It captures EVERY raw scan result the competitor-scan mode collects — not just
# the month-over-month diffs and alerts that competitor_scan_engine.py acts on —
# so that an accumulating corpus exists to mine later. Nothing reads this data
# yet. There is no analysis, no mining, no threshold tuning and no learning loop
# built on top of it; see the "Backlog" note in directive.md.
#
# Because it is unproven, it is OFF by default: every write is gated behind
# EVA_COMPETITOR_DB_STORE_ENABLED (default "false"), so the scheduled monthly
# run behaves exactly as it did before this file existed. Enabling it only adds
# local sqlite writes — no network, no LLM, no added cost.

Why the writes are NOT inside competitor_scan_engine.py: that engine's contract
is to be pure and deterministic (no network, no LLM, no side effects), so the
same snapshot always yields the same verdict. Side-effecting DB writes live at
the boundaries instead — raw per-term results are recorded by competitor_fetch.py
where they are fetched, and verdicts by agent.py where run persistence and ledger
emission already happen.

Note on naming: the `competitor_scan_runs` table here is NOT the same as the
`competitor_scan_runs` table in memory.py. That one is the audit trail of engine
runs (one row per verdict, in memory.db). This one is the raw-capture corpus for
future mining, in its own DB file.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Own DB file, matching the module-owns-its-own-sqlite convention used across
# EVA modules (memory.py here, store.py in activity-tracker-agent, etc.).
DB_PATH = os.environ.get(
    "EVA_COMPETITOR_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "competitor_data.db"),
)

STORE_ENABLED_ENV = "EVA_COMPETITOR_DB_STORE_ENABLED"

# No repo-wide multi-tenant convention exists yet — nothing else in EVA scopes
# rows by project. The column is here so the corpus is already partitioned when
# one arrives, rather than needing a migration over accumulated history.
PROJECT_ID_ENV = "EVA_PROJECT_ID"
FALLBACK_PROJECT_ID = "default"


def is_enabled() -> bool:
    return os.environ.get(STORE_ENABLED_ENV, "false").strip().lower() in ("1", "true", "yes", "on")


def default_project_id() -> str:
    return os.environ.get(PROJECT_ID_ENV) or FALLBACK_PROJECT_ID


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS competitor_scan_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT 'default',
            run_at TEXT NOT NULL,
            term TEXT NOT NULL,
            raw_results_json TEXT NOT NULL,
            agent_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS competitor_scan_verdicts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT 'default',
            run_at TEXT NOT NULL,
            verdict TEXT NOT NULL,
            details_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def record_scan_run(
    project_id: Optional[str],
    term: str,
    raw_results: Any,
    agent_count: int,
) -> Optional[str]:
    """Store one term's FULL fetched result set. Returns the row id, or None when
    the store is disabled (the default), in which case this is a no-op."""
    if not is_enabled():
        return None
    init_db()
    row_id = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO competitor_scan_runs (id, project_id, run_at, term, raw_results_json, agent_count) VALUES (?, ?, ?, ?, ?, ?)",
        (
            row_id,
            project_id or default_project_id(),
            datetime.now(timezone.utc).isoformat(),
            term,
            json.dumps(raw_results, default=str),
            agent_count,
        ),
    )
    conn.commit()
    conn.close()
    return row_id


def record_verdict(project_id: Optional[str], verdict: str, details: Any) -> Optional[str]:
    """Store one scan's verdict plus its full details. Returns the row id, or
    None when the store is disabled (the default), in which case this is a no-op."""
    if not is_enabled():
        return None
    init_db()
    row_id = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO competitor_scan_verdicts (id, project_id, run_at, verdict, details_json) VALUES (?, ?, ?, ?, ?)",
        (
            row_id,
            project_id or default_project_id(),
            datetime.now(timezone.utc).isoformat(),
            verdict,
            json.dumps(details, default=str),
        ),
    )
    conn.commit()
    conn.close()
    return row_id


def list_scan_runs(project_id: Optional[str] = None) -> list[dict]:
    return _list("competitor_scan_runs", "raw_results_json", "raw_results", project_id)


def list_verdicts(project_id: Optional[str] = None) -> list[dict]:
    return _list("competitor_scan_verdicts", "details_json", "details", project_id)


def _list(table: str, json_column: str, decoded_key: str, project_id: Optional[str]) -> list[dict]:
    """Read rows back with the JSON blob decoded. Table names are module
    constants, never caller input; the project filter is parameterised."""
    init_db()
    conn = _connect()
    if project_id is None:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY run_at DESC").fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE project_id = ? ORDER BY run_at DESC", (project_id,)
        ).fetchall()
    conn.close()
    out = []
    for row in rows:
        record = dict(row)
        record[decoded_key] = json.loads(record.pop(json_column))
        out.append(record)
    return out
