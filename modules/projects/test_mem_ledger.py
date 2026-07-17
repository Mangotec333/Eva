"""
EVA Projects — offline memory + ledger test (stdlib only, zero network).

Confirms the Architecture Directive canonical tables:
  * ``memory`` is present and writable (set/get round-trip),
  * ``ledger`` is append-only (UPDATE and DELETE both raise).

Run: python modules/projects/test_mem_ledger.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _assert_ledger_immutable(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO project_ledger (id, ts, event_type) VALUES ('seed','t','ev')")
    conn.commit()
    blocked_update = blocked_delete = False
    try:
        conn.execute("UPDATE project_ledger SET actor='x'")
    except sqlite3.Error as e:
        blocked_update = "append-only" in str(e)
    try:
        conn.execute("DELETE FROM project_ledger")
    except sqlite3.Error as e:
        blocked_delete = "append-only" in str(e)
    conn.close()
    assert blocked_update, "ledger UPDATE was not blocked"
    assert blocked_delete, "ledger DELETE was not blocked"


def test_memory_and_ledger() -> None:
    fd, db = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(db)
    import database as database
    s = database.Store(db)
    s.set_memory("greeting", "hello")
    assert s.get_memory("greeting") == "hello"
    assert s.get_memory("missing", "dflt") == "dflt"
    _assert_ledger_immutable(db)


if __name__ == "__main__":
    test_memory_and_ledger()
    print("OK")
