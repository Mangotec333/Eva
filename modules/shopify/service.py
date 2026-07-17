"""
EVA Shopify — service layer (all enforced rules live here).

The REST API and the CLI both call this one place, so their behavior is
identical (mirrors outreach's ``OutreachService`` / postcards' service).

Responsibilities:
  * Order sync — pull recent orders through the ``ShopifyClient`` (Protocol +
    Stub for offline runs) and upsert them idempotently into local storage.
  * Inventory read — surface current levels.
  * Fulfillment forwarding (dropshipping) — on a synced order, forward the
    order details to the configured supplier/partner via the pluggable
    ``FulfillmentNotifier`` (stub | webhook | email). This is the "fulfill a new
    order" step for a dropshipper and involves no write back to Shopify.
  * Approval gate — every action that WRITES to the live Shopify store (order
    fulfillment status update, inventory level set) is irreversible, so it is
    never executed directly. It is recorded as a ``pending_approval`` and only
    performed once explicitly approved. Reuses the repo's canonical
    pending_approval -> approved -> executed/rejected/failed lifecycle.

Every mutating action appends to the append-only ledger.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from database import (
    APPROVAL_APPROVED,
    APPROVAL_EXECUTED,
    APPROVAL_FAILED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    DB_PATH,
    Store,
)
from config import ShopifyConfig, load_config
from fulfillment import FulfillmentNotifier, build_notifier
from models import ACTION_FULFILL_ORDER, ACTION_SET_INVENTORY, GATED_ACTIONS
from shopify_client import (
    ShopifyClient,
    ShopifyError,
    build_shopify_client,
)


class ShopifyServiceError(Exception):
    """Raised when a rule blocks an action. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


def _normalize_order(raw: dict) -> dict:
    """Map a Shopify order (stub or live) into our storage shape."""
    return {
        "shopify_order_id": str(raw.get("id", "")),
        "name": raw.get("name", "") or "",
        "email": raw.get("email", "") or "",
        "financial_status": raw.get("financial_status", "") or "",
        "fulfillment_status": raw.get("fulfillment_status", "") or "",
        "total_price": str(raw.get("total_price", "") or ""),
        "line_items": raw.get("line_items", []) or [],
        "created_at": raw.get("created_at", "") or "",
        "raw": raw,
    }


class ShopifyService:
    def __init__(
        self,
        store: Optional[Store] = None,
        client: Optional[ShopifyClient] = None,
        notifier: Optional[FulfillmentNotifier] = None,
        config: Optional[ShopifyConfig] = None,
    ):
        self.config = config or load_config()
        self.store = store or Store()
        self.client = client or build_shopify_client(self.config)
        self.notifier = notifier or build_notifier(self.config)

    # ------------------------------------------------------------------
    # Order sync (read — safe, never gated)
    # ------------------------------------------------------------------

    def sync_orders(self, since: str = "", status: str = "any",
                    actor: str = "system") -> dict:
        """Pull recent orders and upsert them locally. Idempotent."""
        try:
            raw_orders = self.client.list_orders(since=since, status=status)
        except ShopifyError as exc:
            raise ShopifyServiceError("shopify_not_connected", str(exc))
        synced = []
        for raw in raw_orders:
            order = self.store.upsert_order(_normalize_order(raw))
            synced.append(order)
        self.store.set_memory(
            "last_sync_at", datetime.now(timezone.utc).isoformat(), source="sync"
        )
        self.store.append_ledger(
            "orders_synced",
            entity_type="orders",
            entity_id="",
            actor=actor,
            details={"count": len(synced), "client": self.client.name,
                     "since": since, "status": status},
        )
        return {"synced": len(synced), "orders": synced, "client": self.client.name}

    def list_orders(self, fulfillment_status: Optional[str] = None) -> list[dict]:
        return self.store.list_orders(fulfillment_status=fulfillment_status)

    def get_order(self, order_id: str) -> dict:
        order = self.store.get_order(order_id)
        if not order:
            raise NotFoundError(f"order {order_id!r} not found")
        return order

    # ------------------------------------------------------------------
    # Inventory (read — safe)
    # ------------------------------------------------------------------

    def get_inventory(self) -> dict:
        try:
            levels = self.client.get_inventory_levels()
        except ShopifyError as exc:
            raise ShopifyServiceError("shopify_not_connected", str(exc))
        return {"inventory": levels, "client": self.client.name}

    # ------------------------------------------------------------------
    # Fulfillment forwarding (dropshipping) — no write back to Shopify
    # ------------------------------------------------------------------

    def forward_order(self, order_id: str, actor: str = "system") -> dict:
        """Forward a synced order to the configured supplier/partner.

        This is the dropshipping "fulfill" step: the order details are handed to
        the supplier who ships the goods. It does not write to the Shopify store,
        so it is not approval-gated — but it fails safe (never fakes a send) when
        the configured transport is not connected."""
        order = self.get_order(order_id)
        order_for_notify = dict(order)
        try:
            order_for_notify["line_items"] = json.loads(order.get("line_items_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            order_for_notify["line_items"] = []
        try:
            order_for_notify["shipping_address"] = json.loads(
                order.get("raw_json", "{}")
            ).get("shipping_address", {})
        except (json.JSONDecodeError, TypeError):
            order_for_notify["shipping_address"] = {}

        result = self.notifier.notify(order_for_notify)
        if result.get("ok"):
            self.store.mark_order_forwarded(order_id)
        self.store.append_ledger(
            "order_forwarded" if result.get("ok") else "order_forward_failed",
            entity_type="order",
            entity_id=order_id,
            actor=actor,
            details={"mode": result.get("mode"), "ok": result.get("ok"),
                     "error": result.get("error", "")},
        )
        return {"order_id": order_id, "result": result}

    # ------------------------------------------------------------------
    # Approval gate — irreversible live writes go here
    # ------------------------------------------------------------------

    def request_fulfillment(self, order_id: str, payload: dict,
                            actor: str = "system") -> dict:
        """Record a live fulfillment-status update as a pending approval.

        The Shopify write is NOT performed here — it only happens when the
        approval is explicitly approved via ``approve``."""
        order = self.get_order(order_id)
        approval = self.store.create_approval(
            action=ACTION_FULFILL_ORDER,
            entity_id=order["shopify_order_id"],
            payload=payload,
            requested_by=actor,
        )
        self.store.append_ledger(
            "approval_requested",
            entity_type="approval",
            entity_id=approval["id"],
            actor=actor,
            details={"action": ACTION_FULFILL_ORDER,
                     "shopify_order_id": order["shopify_order_id"]},
        )
        return approval

    def request_set_inventory(self, inventory_item_id: str, location_id: str,
                              available: int, actor: str = "system") -> dict:
        """Record a live inventory-level change as a pending approval."""
        payload = {
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": available,
        }
        approval = self.store.create_approval(
            action=ACTION_SET_INVENTORY,
            entity_id=inventory_item_id,
            payload=payload,
            requested_by=actor,
        )
        self.store.append_ledger(
            "approval_requested",
            entity_type="approval",
            entity_id=approval["id"],
            actor=actor,
            details={"action": ACTION_SET_INVENTORY, **payload},
        )
        return approval

    def list_approvals(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_approvals(status=status)

    def get_approval(self, approval_id: str) -> dict:
        approval = self.store.get_approval(approval_id)
        if not approval:
            raise NotFoundError(f"approval {approval_id!r} not found")
        return approval

    def reject(self, approval_id: str, approved_by: str = "founder") -> dict:
        approval = self.get_approval(approval_id)
        if approval["status"] != APPROVAL_PENDING:
            raise ShopifyServiceError(
                "not_pending",
                f"approval {approval_id!r} is {approval['status']!r}, not pending",
            )
        updated = self.store.update_approval(
            approval_id, {"status": APPROVAL_REJECTED, "approved_by": approved_by}
        )
        self.store.append_ledger(
            "approval_rejected",
            entity_type="approval",
            entity_id=approval_id,
            actor=approved_by,
            details={"action": approval["action"]},
        )
        return updated

    def approve(self, approval_id: str, approved_by: str = "founder") -> dict:
        """Approve a pending action and execute the live Shopify write.

        This is the ONLY path that performs an irreversible write against the
        live store. It fails safe: if the client is not connected, the approval
        is marked ``failed`` with the error and nothing is silently faked."""
        approval = self.get_approval(approval_id)
        if approval["status"] != APPROVAL_PENDING:
            raise ShopifyServiceError(
                "not_pending",
                f"approval {approval_id!r} is {approval['status']!r}, not pending",
            )

        # Mark approved first (auditable), then execute.
        self.store.update_approval(
            approval_id, {"status": APPROVAL_APPROVED, "approved_by": approved_by}
        )
        self.store.append_ledger(
            "approval_approved",
            entity_type="approval",
            entity_id=approval_id,
            actor=approved_by,
            details={"action": approval["action"]},
        )

        action = approval["action"]
        payload = approval["payload"]
        if action not in GATED_ACTIONS:
            return self._fail_approval(
                approval_id, action, approved_by, f"unknown gated action {action!r}"
            )

        try:
            result = self._execute(action, approval["entity_id"], payload)
        except ShopifyError as exc:
            return self._fail_approval(approval_id, action, approved_by, str(exc))
        except Exception as exc:  # noqa: BLE001 - fail safe, never fake success
            return self._fail_approval(approval_id, action, approved_by, str(exc))

        if not result.get("ok", False):
            return self._fail_approval(
                approval_id, action, approved_by,
                result.get("error", "live write returned not-ok"),
            )

        updated = self.store.update_approval(
            approval_id, {"status": APPROVAL_EXECUTED, "result": result}
        )
        # Reflect the fulfillment locally so a subsequent list is consistent.
        if action == ACTION_FULFILL_ORDER:
            local = self.store.get_order_by_shopify_id(approval["entity_id"])
            if local:
                try:
                    raw = json.loads(local.get("raw_json", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    raw = {}
                self.store.upsert_order({
                    **_normalize_order(raw),
                    "shopify_order_id": approval["entity_id"],
                    "fulfillment_status": payload.get("status", "fulfilled"),
                    "created_at": local.get("created_at", ""),
                })
        self.store.append_ledger(
            "approval_executed",
            entity_type="approval",
            entity_id=approval_id,
            actor=approved_by,
            details={"action": action, "entity_id": approval["entity_id"]},
        )
        return updated

    def _execute(self, action: str, entity_id: str, payload: dict) -> dict:
        """Perform the actual live Shopify write for an approved action."""
        if action == ACTION_FULFILL_ORDER:
            tracking = {}
            if payload.get("tracking_number"):
                tracking = {
                    "tracking_number": payload.get("tracking_number"),
                    "tracking_company": payload.get("tracking_company", ""),
                    "tracking_urls": [payload["tracking_url"]]
                    if payload.get("tracking_url") else [],
                }
            return self.client.update_order_fulfillment_status(
                entity_id, payload.get("status", "fulfilled"),
                tracking=tracking or None,
            )
        if action == ACTION_SET_INVENTORY:
            return self.client.set_inventory_level(
                payload["inventory_item_id"],
                payload["location_id"],
                int(payload["available"]),
            )
        raise ShopifyServiceError("unknown_action", f"unknown action {action!r}")

    def _fail_approval(self, approval_id: str, action: str, actor: str,
                       error: str) -> dict:
        updated = self.store.update_approval(
            approval_id, {"status": APPROVAL_FAILED, "result": {"ok": False, "error": error}}
        )
        self.store.append_ledger(
            "approval_failed",
            entity_type="approval",
            entity_id=approval_id,
            actor=actor,
            details={"action": action, "error": error},
        )
        return updated

    # ------------------------------------------------------------------
    # Memory (Agent Intelligence Layer)
    # ------------------------------------------------------------------

    def set_memory(self, key: str, value: str, source: str = "api") -> dict:
        return self.store.set_memory(key, value, source=source)

    def get_memory(self, key: str) -> Optional[dict]:
        return self.store.get_memory(key)

    def list_memory(self) -> list[dict]:
        return self.store.list_memory()

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    def export_ledger(self, fmt: str = "json") -> str:
        import csv
        import io
        import json

        rows = self.store.query_ledger()
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "ts", "event_type", "entity_type", "entity_id", "actor", "details_json"]
            )
            for r in rows:
                writer.writerow(
                    [r["id"], r["ts"], r["event_type"], r["entity_type"],
                     r["entity_id"], r["actor"], r.get("details_json", "{}")]
                )
            return buf.getvalue()
        return json.dumps(rows, indent=2, default=str)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)
