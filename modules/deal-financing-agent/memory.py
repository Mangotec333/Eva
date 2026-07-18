"""
EVA Deal Financing Agent — sqlite persistence
==============================================
Every run is persisted to agent_runs for audit (same pattern as
deal-analyzer-agent/memory.py, scoped down to this module's needs).
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS financing_runs (
            id TEXT PRIMARY KEY,
            deal_name TEXT NOT NULL,
            input_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_run(run_id: str, deal_name: str, input_json: str, result_json: str, created_at: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO financing_runs (id, deal_name, input_json, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (run_id, deal_name, input_json, result_json, created_at),
    )
    conn.commit()
    conn.close()


def get_run(run_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute("SELECT * FROM financing_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "deal_name": row["deal_name"],
        "input": json.loads(row["input_json"]),
        "result": json.loads(row["result_json"]),
        "created_at": row["created_at"],
    }


def list_runs(deal_name: Optional[str] = None) -> list[dict]:
    conn = _connect()
    if deal_name:
        rows = conn.execute(
            "SELECT id, deal_name, created_at FROM financing_runs WHERE deal_name = ? ORDER BY created_at DESC",
            (deal_name,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT id, deal_name, created_at FROM financing_runs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
