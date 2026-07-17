"""
EVA Shopify — SQLite persistence layer (stdlib sqlite3, sync).

Follows the canonical ``modules/postcards`` / ``modules/outreach`` convention:
stdlib ``sqlite3`` (offline-runnable), a per-agent ``memory`` table, and an
append-only ``ledger`` table made immutable with BEFORE UPDATE / BEFORE DELETE
triggers (exactly the postcards ``publish_ledger`` pattern).

Tables:
  * ``orders``            — synced Shopify orders + local fulfillment state.
  * ``pending_approvals`` — irreversible live-write actions awaiting approval
                            (the approval-gate mechanism; mirrors the
                            draft->approved->executed flow used elsewhere).
  * ``memory``            — per-agent key/value memory (Agent Intelligence Layer).
  * ``ledger``            — append-only event trail (immutable via trigger).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "EVA_SHOPIFY_DB",
    os.path.join(os.path.dirname(__file__), "eva-shopify.db"),
)

# pending_approvals.status lifecycle
APPROVAL_PENDING = "pending_approval"
APPROVAL_APPROVED = "approved"
APPROVAL_EXECUTED = "executed"
APPROVAL_REJECTED = "rejected"
APPROVAL_FAILED = "failed"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id                 TEXT PRIMARY KEY,
    shopify_order_id   TEXT NOT NULL,
    name               TEXT NOT NULL DEFAULT '',
    email              TEXT NOT NULL DEFAULT '',
    financial_status   TEXT NOT NULL DEFAULT '',
    fulfillment_status TEXT NOT NULL DEFAULT '',
    total_price        TEXT NOT NULL DEFAULT '',
    line_items_json    TEXT NOT NULL DEFAULT '[]',
    raw_json           TEXT NOT NULL DEFAULT '{}',
    forwarded          INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT '',
    synced_at          TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id            TEXT PRIMARY KEY,
    action        TEXT NOT NULL,
    entity_id     TEXT NOT NULL DEFAULT '',
    payload_json  TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'pending_approval',
    result_json   TEXT NOT NULL DEFAULT '{}',
    requested_by  TEXT NOT NULL DEFAULT '',
    approved_by   TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_shopify_id ON orders(shopify_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_fulfillment ON orders(fulfillment_status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals(status);

-- The ledger is append-only: block UPDATE and DELETE (canonical pattern).
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


class Store:
    """Thin sync sqlite3 data-access layer. Opens a fresh connection per op."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- orders -------------------------------------------------------------

    def upsert_order(self, order: dict) -> dict:
        """Insert or update a synced order (idempotent on shopify_order_id)."""
        ts = _now()
        existing = self.get_order_by_shopify_id(order["shopify_order_id"])
        row = {
            "id": existing["id"] if existing else str(uuid.uuid4()),
            "shopify_order_id": order["shopify_order_id"],
            "name": order.get("name", ""),
            "email": order.get("email", ""),
            "financial_status": order.get("financial_status", "") or "",
            "fulfillment_status": order.get("fulfillment_status", "") or "",
            "total_price": order.get("total_price", ""),
            "line_items_json": json.dumps(order.get("line_items", [])),
            "raw_json": json.dumps(order.get("raw", {})),
            "forwarded": existing["forwarded"] if existing else 0,
            "created_at": order.get("created_at", "") or (existing["created_at"] if existing else ""),
            "synced_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO orders
                   (id, shopify_order_id, name, email, financial_status,
                    fulfillment_status, total_price, line_items_json, raw_json,
                    forwarded, created_at, synced_at, updated_at)
                   VALUES (:id, :shopify_order_id, :name, :email, :financial_status,
                           :fulfillment_status, :total_price, :line_items_json,
                           :raw_json, :forwarded, :created_at, :synced_at, :updated_at)
                   ON CONFLICT(shopify_order_id) DO UPDATE SET
                     name=excluded.name, email=excluded.email,
                     financial_status=excluded.financial_status,
                     fulfillment_status=excluded.fulfillment_status,
                     total_price=excluded.total_price,
                     line_items_json=excluded.line_items_json,
                     raw_json=excluded.raw_json, synced_at=excluded.synced_at,
                     updated_at=excluded.updated_at""",
                row,
            )
        return self.get_order_by_shopify_id(order["shopify_order_id"])

    def get_order(self, order_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(r) if r else None

    def get_order_by_shopify_id(self, shopify_order_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM orders WHERE shopify_order_id = ? LIMIT 1",
                (shopify_order_id,),
            ).fetchone()
        return dict(r) if r else None

    def list_orders(self, fulfillment_status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if fulfillment_status is not None:
            clauses.append("fulfillment_status = ?")
            params.append(fulfillment_status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM orders {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_order_forwarded(self, order_id: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET forwarded = 1, updated_at = ? WHERE id = ?",
                (_now(), order_id),
            )
        return self.get_order(order_id)

    # -- pending approvals (approval gate) ---------------------------------

    def create_approval(self, action: str, entity_id: str, payload: dict,
                        requested_by: str = "system") -> dict:
        ts = _now()
        row = {
            "id": str(uuid.uuid4()),
            "action": action,
            "entity_id": entity_id,
            "payload_json": json.dumps(payload),
            "status": APPROVAL_PENDING,
            "result_json": "{}",
            "requested_by": requested_by,
            "approved_by": "",
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO pending_approvals
                   (id, action, entity_id, payload_json, status, result_json,
                    requested_by, approved_by, created_at, updated_at)
                   VALUES (:id, :action, :entity_id, :payload_json, :status,
                           :result_json, :requested_by, :approved_by,
                           :created_at, :updated_at)""",
                row,
            )
        return self.get_approval(row["id"])

    def get_approval(self, approval_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        if not r:
            return None
        d = dict(r)
        d["payload"] = json.loads(d.get("payload_json", "{}") or "{}")
        d["result"] = json.loads(d.get("result_json", "{}") or "{}")
        return d

    def list_approvals(self, status: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM pending_approvals {where} ORDER BY created_at", params
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.get("payload_json", "{}") or "{}")
            d["result"] = json.loads(d.get("result_json", "{}") or "{}")
            out.append(d)
        return out

    def update_approval(self, approval_id: str, fields: dict) -> Optional[dict]:
        if not fields:
            return self.get_approval(approval_id)
        cols = dict(fields)
        if "result" in cols:
            cols["result_json"] = json.dumps(cols.pop("result"))
        cols["updated_at"] = _now()
        assignments = ", ".join(f"{k} = :{k}" for k in cols)
        cols["id"] = approval_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE pending_approvals SET {assignments} WHERE id = :id", cols
            )
        return self.get_approval(approval_id)

    # -- memory -------------------------------------------------------------

    def get_memory(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM memory WHERE key = ?", (key,)).fetchone()
        return dict(r) if r else None

    def get_memory_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.get_memory(key)
        return row["value"] if row else default

    def set_memory(self, key: str, value: str, source: str = "system") -> dict:
        row = {"key": key, "value": value, "ts": _now(), "source": source}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, ts, source)
                   VALUES (:key, :value, :ts, :source)
                   ON CONFLICT(key) DO UPDATE SET
                     value=excluded.value, ts=excluded.ts, source=excluded.source""",
                row,
            )
        return row

    def list_memory(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory ORDER BY key").fetchall()
        return [dict(r) for r in rows]

    # -- ledger (append-only) ----------------------------------------------

    def append_ledger(self, event_type: str, entity_type: str = "",
                     entity_id: str = "", actor: str = "",
                     details: Optional[dict] = None) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor": actor,
            "details_json": json.dumps(details or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO ledger
                   (id, ts, event_type, entity_type, entity_id, actor, details_json)
                   VALUES (:id, :ts, :event_type, :entity_type, :entity_id,
                           :actor, :details_json)""",
                row,
            )
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json"))
        return out

    def query_ledger(self, from_ts: Optional[str] = None, to_ts: Optional[str] = None,
                    event_type: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if from_ts:
            clauses.append("ts >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("ts <= ?")
            params.append(to_ts)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM ledger {where} ORDER BY ts ASC", params
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
            out.append(d)
        return out
