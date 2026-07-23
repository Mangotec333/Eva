"""
EVA Treasurer — ``TreasurerStore`` persistence (stdlib ``sqlite3``, sync).

STRICT PERSONAL vs. BUSINESS SEPARATION
---------------------------------------
This is the load-bearing invariant of the module. Separation is *structural*,
not a query-time flag:

  * Each ``side`` ("personal" / "business") is backed by its OWN SQLite database
    file (``treasurer_personal.db`` / ``treasurer_business.db``).
  * A ``TreasurerStore`` instance is bound to exactly one ``side`` and one
    database path at construction time. There is no code path that opens both
    databases on one connection, and no query that unions the two.
  * Every row written carries its ``side``, and the store REFUSES to persist a
    row whose ``side`` disagrees with the store's own side. So even a
    mis-labeled inbound record cannot cross the boundary.

Use ``open_side(side)`` (the env-driven factory) to obtain a store for one side.
To touch both sides you must open two separate stores — by design.

Dedup: transactions are unique on ``(account_id, dedup_key)``. When a provider
does not supply a ``dedup_key`` we derive a stable one from
``(account_id, posted_date, amount_cents, description)`` so re-running an import
never double-counts.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from models import CREDIT_ACCOUNT_TYPES, VALID_SIDES

# Default on-disk locations (gitignored). Overridable via env for tests/ops.
DB_PATHS = {
    "personal": os.environ.get(
        "TREASURER_PERSONAL_DB",
        os.path.join(os.path.dirname(__file__), "treasurer_personal.db"),
    ),
    "business": os.environ.get(
        "TREASURER_BUSINESS_DB",
        os.path.join(os.path.dirname(__file__), "treasurer_business.db"),
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def derive_dedup_key(account_id: str, posted_date: str, amount_cents: int,
                     description: str) -> str:
    """Stable idempotency key for a transaction when the provider gives none."""
    raw = f"{account_id}|{posted_date}|{amount_cents}|{description}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto dedup


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id                  TEXT PRIMARY KEY,
    side                TEXT NOT NULL,
    institution         TEXT NOT NULL DEFAULT '',
    name                TEXT NOT NULL,
    account_type        TEXT NOT NULL DEFAULT 'checking',
    external_id         TEXT NOT NULL DEFAULT '',
    credit_limit_cents  INTEGER NOT NULL DEFAULT 0,
    balance_cents       INTEGER NOT NULL DEFAULT 0,
    currency            TEXT NOT NULL DEFAULT 'USD',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(side, institution, name)
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  TEXT PRIMARY KEY,
    side                TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    posted_date         TEXT NOT NULL,
    amount_cents        INTEGER NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    category            TEXT NOT NULL DEFAULT 'uncategorized',
    dedup_key           TEXT NOT NULL,
    provider            TEXT NOT NULL DEFAULT 'manual',
    created_at          TEXT NOT NULL,
    UNIQUE(account_id, dedup_key)
);

CREATE TABLE IF NOT EXISTS categorization_rules (
    id                  TEXT PRIMARY KEY,
    side                TEXT NOT NULL,
    match_type          TEXT NOT NULL DEFAULT 'contains',
    pattern             TEXT NOT NULL,
    category            TEXT NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 100,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bills (
    id                  TEXT PRIMARY KEY,
    side                TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    due_date            TEXT NOT NULL,
    amount_due_cents    INTEGER NOT NULL DEFAULT 0,
    minimum_payment_cents INTEGER NOT NULL DEFAULT 0,
    paid                INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);
"""


class TreasurerStore:
    """Single-side persistence surface. Bound to one ``side`` + one db file."""

    def __init__(self, side: str, db_path: str):
        if side not in VALID_SIDES:
            raise ValueError(f"invalid side {side!r}; must be one of {VALID_SIDES}")
        self.side = side
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    # -- lifecycle ----------------------------------------------------------

    def migrate(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _guard_side(self, side: Optional[str]) -> None:
        """Reject any write whose side disagrees with this store's side."""
        if side is not None and side != self.side:
            raise ValueError(
                f"cross-side write blocked: {side!r} row rejected by "
                f"{self.side!r} store"
            )

    # -- accounts -----------------------------------------------------------

    def upsert_account(self, *, institution: str, name: str,
                       account_type: str = "checking", external_id: str = "",
                       credit_limit_cents: int = 0, balance_cents: int = 0,
                       currency: str = "USD", side: Optional[str] = None) -> dict:
        self._guard_side(side)
        now = _now()
        cur = self._conn.execute(
            "SELECT id FROM accounts WHERE side=? AND institution=? AND name=?",
            (self.side, institution, name),
        )
        row = cur.fetchone()
        if row:
            acc_id = row["id"]
            self._conn.execute(
                """UPDATE accounts SET account_type=?, external_id=?,
                       credit_limit_cents=?, balance_cents=?, currency=?, updated_at=?
                   WHERE id=?""",
                (account_type, external_id, credit_limit_cents, balance_cents,
                 currency, now, acc_id),
            )
        else:
            acc_id = _new_id()
            self._conn.execute(
                """INSERT INTO accounts
                   (id, side, institution, name, account_type, external_id,
                    credit_limit_cents, balance_cents, currency, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (acc_id, self.side, institution, name, account_type, external_id,
                 credit_limit_cents, balance_cents, currency, now, now),
            )
        self._conn.commit()
        return self.get_account(acc_id)

    def get_account(self, account_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT * FROM accounts WHERE id=? AND side=?", (account_id, self.side)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def find_account_by_external_id(self, external_id: str) -> Optional[dict]:
        if not external_id:
            return None
        cur = self._conn.execute(
            "SELECT * FROM accounts WHERE side=? AND external_id=?",
            (self.side, external_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_accounts(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM accounts WHERE side=? ORDER BY institution, name",
            (self.side,),
        )
        return [dict(r) for r in cur.fetchall()]

    def set_balance(self, account_id: str, balance_cents: int) -> None:
        self._conn.execute(
            "UPDATE accounts SET balance_cents=?, updated_at=? WHERE id=? AND side=?",
            (balance_cents, _now(), account_id, self.side),
        )
        self._conn.commit()

    # -- transactions -------------------------------------------------------

    def add_transaction(self, *, account_id: str, posted_date: str,
                        amount_cents: int, description: str = "",
                        category: str = "uncategorized", dedup_key: str = "",
                        provider: str = "manual",
                        side: Optional[str] = None) -> dict:
        """Insert a transaction. Idempotent on (account_id, dedup_key).

        Returns ``{"inserted": bool, "transaction": dict}``.
        """
        self._guard_side(side)
        if self.get_account(account_id) is None:
            raise ValueError(f"unknown account_id {account_id!r} for side {self.side!r}")
        if not dedup_key:
            dedup_key = derive_dedup_key(account_id, posted_date, amount_cents, description)

        cur = self._conn.execute(
            "SELECT * FROM transactions WHERE account_id=? AND dedup_key=?",
            (account_id, dedup_key),
        )
        existing = cur.fetchone()
        if existing:
            return {"inserted": False, "transaction": dict(existing)}

        txn_id = _new_id()
        now = _now()
        self._conn.execute(
            """INSERT INTO transactions
               (id, side, account_id, posted_date, amount_cents, description,
                category, dedup_key, provider, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (txn_id, self.side, account_id, posted_date, amount_cents, description,
             category, dedup_key, provider, now),
        )
        self._conn.commit()
        return {"inserted": True, "transaction": self.get_transaction(txn_id)}

    def get_transaction(self, txn_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT * FROM transactions WHERE id=? AND side=?", (txn_id, self.side)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_transactions(self, *, account_id: Optional[str] = None,
                          start: Optional[str] = None,
                          end: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM transactions WHERE side=?"
        params: list[Any] = [self.side]
        if account_id:
            query += " AND account_id=?"
            params.append(account_id)
        if start:
            query += " AND posted_date>=?"
            params.append(start)
        if end:
            query += " AND posted_date<=?"
            params.append(end)
        query += " ORDER BY posted_date DESC, created_at DESC"
        cur = self._conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def set_transaction_category(self, txn_id: str, category: str) -> None:
        self._conn.execute(
            "UPDATE transactions SET category=? WHERE id=? AND side=?",
            (category, txn_id, self.side),
        )
        self._conn.commit()

    # -- categorization rules ----------------------------------------------

    def add_rule(self, *, match_type: str, pattern: str, category: str,
                 priority: int = 100, side: Optional[str] = None) -> dict:
        self._guard_side(side)
        rule_id = _new_id()
        self._conn.execute(
            """INSERT INTO categorization_rules
               (id, side, match_type, pattern, category, priority, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (rule_id, self.side, match_type, pattern, category, priority, _now()),
        )
        self._conn.commit()
        return self.get_rule(rule_id)

    def get_rule(self, rule_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT * FROM categorization_rules WHERE id=? AND side=?",
            (rule_id, self.side),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_rules(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM categorization_rules WHERE side=? ORDER BY priority ASC, created_at ASC",
            (self.side,),
        )
        return [dict(r) for r in cur.fetchall()]

    # -- bills --------------------------------------------------------------

    def add_bill(self, *, account_id: str, name: str, due_date: str,
                 amount_due_cents: int = 0, minimum_payment_cents: int = 0,
                 side: Optional[str] = None) -> dict:
        self._guard_side(side)
        if self.get_account(account_id) is None:
            raise ValueError(f"unknown account_id {account_id!r} for side {self.side!r}")
        bill_id = _new_id()
        self._conn.execute(
            """INSERT INTO bills
               (id, side, account_id, name, due_date, amount_due_cents,
                minimum_payment_cents, paid, created_at)
               VALUES (?,?,?,?,?,?,?,0,?)""",
            (bill_id, self.side, account_id, name, due_date, amount_due_cents,
             minimum_payment_cents, _now()),
        )
        self._conn.commit()
        return self.get_bill(bill_id)

    def get_bill(self, bill_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT * FROM bills WHERE id=? AND side=?", (bill_id, self.side)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_bills(self, *, include_paid: bool = False) -> list[dict]:
        query = "SELECT * FROM bills WHERE side=?"
        if not include_paid:
            query += " AND paid=0"
        query += " ORDER BY due_date ASC"
        cur = self._conn.execute(query, (self.side,))
        return [dict(r) for r in cur.fetchall()]

    def mark_bill_paid(self, bill_id: str, paid: bool = True) -> None:
        self._conn.execute(
            "UPDATE bills SET paid=? WHERE id=? AND side=?",
            (1 if paid else 0, bill_id, self.side),
        )
        self._conn.commit()

    # -- convenience --------------------------------------------------------

    def credit_accounts(self) -> list[dict]:
        """Accounts that carry a credit limit (subject to utilization checks)."""
        return [
            a for a in self.list_accounts()
            if a["account_type"] in CREDIT_ACCOUNT_TYPES and a["credit_limit_cents"] > 0
        ]


def open_side(side: str) -> TreasurerStore:
    """Env-driven factory: open (and migrate) the store for one side.

    The database path comes from ``TREASURER_PERSONAL_DB`` /
    ``TREASURER_BUSINESS_DB`` (see ``DB_PATHS``), guaranteeing the two sides can
    never share a file.
    """
    if side not in VALID_SIDES:
        raise ValueError(f"invalid side {side!r}; must be one of {VALID_SIDES}")
    store = TreasurerStore(side, DB_PATHS[side])
    store.migrate()
    return store
