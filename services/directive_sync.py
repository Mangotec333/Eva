"""Directive-sync bridge — the nervous-system feedback path.

This is how conversations, decisions, and learnings get fed BACK into an
autonomous agent. The router/executor push work OUT to agents; this bridge
pushes distilled knowledge IN, closing the loop.

Two surfaces:

- ``sync_directive(agent_name, updates)`` — append a timestamped, structured
  entry to that agent's ``directive.md`` under a ``## LEARNINGS (auto-synced)``
  section, and record a new ``directive_version`` row in the agent's
  ``memory.db``. This is the single write primitive.
- ``sync_loop(inbox_path)`` — poll a shared file inbox
  (``data/directive_inbox.jsonl``) for incoming decisions and apply each via
  ``sync_directive``. A cursor file tracks progress so entries are applied
  exactly once across restarts.

Deliberately file-based: no new service, no broker, no network. A conversation
turn (or the learning loop) appends one JSON line to the inbox; the loop drains
it into the relevant agent's live directive.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODULES_DIR = os.path.join(_REPO_ROOT, "modules")
INBOX_PATH = os.path.join(_REPO_ROOT, "data", "directive_inbox.jsonl")

LEARNINGS_HEADER = "## LEARNINGS (auto-synced)"

_DIRECTIVE_VERSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS directive_versions (
    id         TEXT PRIMARY KEY,
    version    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Agent path resolution
# ---------------------------------------------------------------------------

def agent_dir(agent_name: str, modules_dir: str = MODULES_DIR) -> str:
    """Resolve an agent's module directory under ``modules/``."""
    return os.path.join(modules_dir, agent_name)


def directive_path(agent_name: str, modules_dir: str = MODULES_DIR) -> str:
    return os.path.join(agent_dir(agent_name, modules_dir), "directive.md")


def memory_db_path(agent_name: str, modules_dir: str = MODULES_DIR) -> str:
    return os.path.join(agent_dir(agent_name, modules_dir), "memory.db")


# ---------------------------------------------------------------------------
# Formatting + append
# ---------------------------------------------------------------------------

def _format_entry(updates: dict, ts: str) -> str:
    """Render an inbound update dict into a markdown learnings entry."""
    lines = [f"### {ts}"]
    source = updates.get("source")
    if source:
        lines.append(f"- **source**: {source}")
    for key in ("deal", "deal_id", "outcome", "lesson", "decision"):
        if updates.get(key) not in (None, ""):
            lines.append(f"- **{key}**: {updates[key]}")
    if updates.get("weight_delta"):
        lines.append(f"- **weight_delta**: `{json.dumps(updates['weight_delta'])}`")
    # Anything not already rendered above is captured verbatim so nothing is lost.
    rendered = {"source", "deal", "deal_id", "outcome", "lesson", "decision", "weight_delta"}
    extra = {k: v for k, v in updates.items() if k not in rendered}
    if extra:
        lines.append(f"- **extra**: `{json.dumps(extra, default=str)}`")
    return "\n".join(lines) + "\n"


def _append_under_header(body: str, header: str, entry: str) -> str:
    """Insert ``entry`` immediately after ``header`` in ``body``.

    Creates the header at end-of-file when absent. Keeps existing entries; new
    entries are placed right below the header (most-recent-first).
    """
    if header not in body:
        sep = "" if body.endswith("\n") or not body else "\n"
        return f"{body}{sep}\n{header}\n\n{entry}"
    head, _, tail = body.partition(header)
    tail = tail.lstrip("\n")
    return f"{head}{header}\n\n{entry}\n{tail}"


def _record_directive_version(db_path: str, version: str, content: str) -> str:
    """Insert a directive_versions row into the agent's memory.db.

    Writes directly via sqlite3 (rather than importing the agent's flat memory
    module) so the bridge stays decoupled from any single agent's package.
    """
    row_id = str(uuid.uuid4())
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_DIRECTIVE_VERSIONS_SCHEMA)
        conn.execute(
            "INSERT INTO directive_versions (id, version, content, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (row_id, version, content, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return row_id


def sync_directive(
    agent_name: str,
    updates: dict,
    *,
    modules_dir: str = MODULES_DIR,
    now: Optional[str] = None,
) -> dict:
    """Append a learnings entry to an agent's directive and version its memory.

    Returns a summary: the agent, the directive version string, the row id, and
    the appended entry text.
    """
    ts = now or _now()
    entry = _format_entry(updates, ts)

    dpath = directive_path(agent_name, modules_dir)
    try:
        with open(dpath, "r", encoding="utf-8") as fh:
            body = fh.read()
    except FileNotFoundError:
        body = f"# {agent_name} — Live Directive\n"
    new_body = _append_under_header(body, LEARNINGS_HEADER, entry)
    os.makedirs(os.path.dirname(dpath) or ".", exist_ok=True)
    with open(dpath, "w", encoding="utf-8") as fh:
        fh.write(new_body)

    version = f"synced-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    row_id = _record_directive_version(
        memory_db_path(agent_name, modules_dir), version, entry,
    )
    return {
        "agent": agent_name,
        "version": version,
        "row_id": row_id,
        "directive_path": dpath,
        "entry": entry,
    }


# ---------------------------------------------------------------------------
# Inbox watch loop
# ---------------------------------------------------------------------------

def _cursor_path(inbox_path: str) -> str:
    return inbox_path + ".cursor"


def _read_cursor(inbox_path: str) -> int:
    try:
        with open(_cursor_path(inbox_path), "r", encoding="utf-8") as fh:
            return int(fh.read().strip() or "0")
    except (FileNotFoundError, ValueError):
        return 0


def _write_cursor(inbox_path: str, n: int) -> None:
    with open(_cursor_path(inbox_path), "w", encoding="utf-8") as fh:
        fh.write(str(n))


def drain_inbox(inbox_path: str = INBOX_PATH, *, modules_dir: str = MODULES_DIR) -> list[dict]:
    """Apply any un-processed inbox lines, advancing the cursor. Returns results.

    Each inbox line is a JSON object ``{"agent": <name>, "updates": {...}}`` (a
    bare ``{...}`` with an ``agent`` key inline is also accepted). Malformed
    lines are skipped but still counted so the cursor never stalls on bad input.
    """
    if not os.path.exists(inbox_path):
        return []
    with open(inbox_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    start = _read_cursor(inbox_path)
    results: list[dict] = []
    for line in lines[start:]:
        line = line.strip()
        if line:
            try:
                msg = json.loads(line)
                agent = msg.get("agent")
                updates = msg.get("updates", {k: v for k, v in msg.items() if k != "agent"})
                if agent:
                    results.append(sync_directive(agent, updates, modules_dir=modules_dir))
            except (json.JSONDecodeError, OSError) as exc:
                results.append({"error": str(exc), "line": line[:200]})
    _write_cursor(inbox_path, len(lines))
    return results


def sync_loop(
    inbox_path: str = INBOX_PATH,
    *,
    modules_dir: str = MODULES_DIR,
    interval_s: float = 30.0,
    max_iterations: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Continuous watch loop: drain the inbox each tick, applying new decisions.

    Runs forever by default; pass ``max_iterations`` to bound it (tests, cron
    ticks). This is the real loop — it iterates and sleeps between drains — with
    only the inbox *source* being a file stub any producer can append to.
    """
    iterations = 0
    applied = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        applied += len(drain_inbox(inbox_path, modules_dir=modules_dir))
        if max_iterations is None or iterations < max_iterations:
            sleep(interval_s)
    return {"iterations": iterations, "applied": applied}


def enqueue(agent_name: str, updates: dict, inbox_path: str = INBOX_PATH) -> None:
    """Append one decision to the inbox (the producer side, for convenience)."""
    os.makedirs(os.path.dirname(inbox_path) or ".", exist_ok=True)
    with open(inbox_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"agent": agent_name, "updates": updates}, default=str) + "\n")


__all__ = [
    "sync_directive",
    "sync_loop",
    "drain_inbox",
    "enqueue",
    "directive_path",
    "memory_db_path",
    "LEARNINGS_HEADER",
]
