"""
EVA Local-Exec — SQLite persistence for the full run audit + approval gate.

One table, ``runs``, is the local, tamper-evident audit trail of every command
Eva ever asked the Mac to run — allowlisted auto-runs, approved runs, blocked /
pending gates, failures, denials, and approval timeouts alike. It doubles as the
pending-approval queue: a non-allowlisted command is written as ``pending`` and
flipped to ``approved`` / ``denied`` / ``expired`` in place, so a launcher/CLI
restart never loses an in-flight approval.

Everything stored here is already secret-masked by ``exec.py`` before it lands
(stdout/stderr/command/args) — no raw secret is ever written to disk. The DB
lives beside this module and is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "LOCAL_EXEC_DB",
    os.path.join(os.path.dirname(__file__), "local_exec.db"),
)

# Run lifecycle / audit statuses.
STATUS_ALLOWLISTED = "allowlisted"   # matched allowlist → auto-ran
STATUS_PENDING = "pending"           # awaiting one-tap approval
STATUS_APPROVED = "approved"         # approved → ran
STATUS_DENIED = "denied"             # explicitly denied → never ran
STATUS_BLOCKED = "blocked"           # created a pending gate (audit marker)
STATUS_FAILED = "failed"             # ran but exited non-zero / errored
STATUS_EXPIRED = "expired"           # approval timed out → never ran

HISTORY_MAX = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id             TEXT PRIMARY KEY,
                ts             TEXT NOT NULL,
                command        TEXT NOT NULL DEFAULT '',
                args           TEXT NOT NULL DEFAULT '[]',
                cwd            TEXT NOT NULL DEFAULT '',
                exit_code      INTEGER,
                stdout_masked  TEXT NOT NULL DEFAULT '',
                stderr_masked  TEXT NOT NULL DEFAULT '',
                duration       REAL NOT NULL DEFAULT 0,
                status         TEXT NOT NULL DEFAULT 'pending',
                triggered_by   TEXT NOT NULL DEFAULT 'eva',
                rule           TEXT NOT NULL DEFAULT '',
                masked         INTEGER NOT NULL DEFAULT 0,
                expires_at     TEXT NOT NULL DEFAULT '',
                updated_at     TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["args"] = json.loads(d.get("args") or "[]")
    d["masked"] = bool(d.get("masked"))
    return d


def create_run(*, command: str, args: list[str], cwd: str, status: str,
               triggered_by: str = "eva", rule: str = "",
               exit_code: int | None = None, stdout_masked: str = "",
               stderr_masked: str = "", duration: float = 0.0,
               masked: bool = False, expires_at: str = "",
               path: str | None = None) -> dict:
    """Insert one audit row. Everything passed in is assumed already masked."""
    init_db(path)
    rid = str(uuid.uuid4())
    now = _now()
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO runs
               (id, ts, command, args, cwd, exit_code, stdout_masked,
                stderr_masked, duration, status, triggered_by, rule, masked,
                expires_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, now, command, json.dumps(args or []), cwd or "", exit_code,
             stdout_masked, stderr_masked, duration, status, triggered_by, rule,
             1 if masked else 0, expires_at, now),
        )
        conn.commit()
    return get_run(rid, path=path)


def update_run(run_id: str, fields: dict, path: str | None = None) -> dict | None:
    init_db(path)
    if not fields:
        return get_run(run_id, path=path)
    cols, vals = [], []
    for k, v in fields.items():
        if k == "args":
            v = json.dumps(v or [])
        if k == "masked":
            v = 1 if v else 0
        cols.append(f"{k}=?")
        vals.append(v)
    cols.append("updated_at=?")
    vals.append(_now())
    vals.append(run_id)
    with _connect(path) as conn:
        conn.execute(f"UPDATE runs SET {', '.join(cols)} WHERE id=?", vals)
        conn.commit()
    return get_run(run_id, path=path)


def get_run(run_id: str, path: str | None = None) -> dict | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_runs(limit: int = 50, status: str | None = None,
              path: str | None = None) -> list[dict]:
    """Recent runs, newest first, capped."""
    init_db(path)
    limit = max(1, min(limit, HISTORY_MAX))
    with _connect(path) as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM runs WHERE status=? ORDER BY ts DESC LIMIT ?",
                (status, limit))
        else:
            cur = conn.execute(
                "SELECT * FROM runs ORDER BY ts DESC LIMIT ?", (limit,))
        return [_row_to_dict(r) for r in cur.fetchall()]


def count_by_status(path: str | None = None) -> dict:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute("SELECT status, COUNT(*) c FROM runs GROUP BY status")
        return {r["status"]: r["c"] for r in cur.fetchall()}


__all__ = [
    "DB_PATH", "HISTORY_MAX",
    "STATUS_ALLOWLISTED", "STATUS_PENDING", "STATUS_APPROVED", "STATUS_DENIED",
    "STATUS_BLOCKED", "STATUS_FAILED", "STATUS_EXPIRED",
    "init_db", "create_run", "update_run", "get_run", "list_runs",
    "count_by_status",
]
