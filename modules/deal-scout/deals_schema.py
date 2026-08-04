"""
EVA Deal Scout — additive schema migrations + grouping helpers for the legacy
``deals`` table.

``database.py`` owns the async aiosqlite access path; this module holds the
parts that are pure stdlib so the column migration and the pass-reason
aggregation can be exercised directly by the test-suite.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Sequence

# Columns added to ``deals`` after the original CREATE statement shipped.  Each
# entry is applied only when the column is missing, so a fresh DB (created with
# the current CREATE_DEALS_SQL) and an existing one converge on the same shape.
DEAL_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("status", "ALTER TABLE deals ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
    ("pass_reason", "ALTER TABLE deals ADD COLUMN pass_reason TEXT"),
)


def pending_deal_column_sql(existing_columns: Iterable[str]) -> list[str]:
    """ALTER statements needed to bring ``deals`` up to the current shape."""
    have = set(existing_columns)
    return [sql for column, sql in DEAL_COLUMN_MIGRATIONS if column not in have]


def migrate_deals_table(conn: sqlite3.Connection) -> list[str]:
    """Apply the pending column migrations to a stdlib sqlite3 connection.

    Returns the statements applied (empty on a second run — this is idempotent).
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(deals)").fetchall()]
    statements = pending_deal_column_sql(cols)
    for sql in statements:
        conn.execute(sql)
    conn.commit()
    return statements


def group_passed_deals(deals: Sequence[dict]) -> dict[str, Any]:
    """Group passed deals by ``pass_reason`` with a count and the deals themselves.

    Reasons are ordered by count descending so the most common rejection
    pattern reads first.  Rows persisted before ``pass_reason`` existed (or set
    directly in the DB) fall into the ``"unspecified"`` bucket.
    """
    groups: dict[str, list[dict]] = {}
    for deal in deals:
        reason = deal.get("pass_reason") or "unspecified"
        groups.setdefault(reason, []).append(deal)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {
        "total": len(deals),
        "reason_counts": {reason: len(rows) for reason, rows in ordered},
        "groups": [
            {"pass_reason": reason, "count": len(rows), "deals": rows}
            for reason, rows in ordered
        ],
    }
