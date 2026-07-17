"""
EVA Shopify — Admin API transport (the single network chokepoint).

All Shopify Admin API I/O lives behind a ``ShopifyClient`` Protocol with:
  * ``StubShopifyClient`` — offline, canned orders/inventory. No network. Used in
    tests and whenever live credentials are absent.
  * ``RealShopifyClient`` — the actual Admin REST API calls (httpx). This is the
    only place real Shopify network code lives.

Read operations (list_orders, get_inventory_levels) are safe. Write operations
(update_order_fulfillment_status, set_inventory_level) are irreversible against a
live store, so the *service layer* routes them through the approval gate — the
client just performs the call once approved. An unwired real client never fakes
success: a missing store/token raises ``ShopifyNotConnectedError``.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from config import ShopifyConfig


class ShopifyError(RuntimeError):
    """Generic Shopify transport error."""


class ShopifyNotConnectedError(ShopifyError):
    """Raised when a live call is attempted without store domain + token."""


@runtime_checkable
class ShopifyClient(Protocol):
    name: str

    def list_orders(self, since: str = "", status: str = "any") -> list[dict]: ...

    def get_inventory_levels(self) -> list[dict]: ...

    def update_order_fulfillment_status(
        self, order_id: str, status: str, tracking: Optional[dict] = None
    ) -> dict: ...

    def set_inventory_level(
        self, inventory_item_id: str, location_id: str, available: int
    ) -> dict: ...


# ---------------------------------------------------------------------------
# Stub (offline, canned) — used in tests + when not live-ready. No network.
# ---------------------------------------------------------------------------

class StubShopifyClient:
    """Offline ShopifyClient with canned data. Records writes in-memory so tests
    can assert what *would* have been sent to the live store."""

    name = "stub"

    def __init__(
        self,
        orders: Optional[list[dict]] = None,
        inventory: Optional[list[dict]] = None,
    ):
        self.orders: list[dict] = orders if orders is not None else [
            {
                "id": "5001",
                "name": "#1001",
                "created_at": "2026-07-16T14:05:00Z",
                "financial_status": "paid",
                "fulfillment_status": None,
                "email": "buyer1@example.com",
                "total_price": "39.99",
                "line_items": [
                    {"sku": "WIDGET-BLK", "title": "Black Widget", "quantity": 1,
                     "inventory_item_id": "inv-blk", "price": "39.99"},
                ],
                "shipping_address": {"name": "Buyer One", "city": "Oxnard", "country": "US"},
            },
            {
                "id": "5002",
                "name": "#1002",
                "created_at": "2026-07-17T09:22:00Z",
                "financial_status": "paid",
                "fulfillment_status": None,
                "email": "buyer2@example.com",
                "total_price": "79.98",
                "line_items": [
                    {"sku": "WIDGET-RED", "title": "Red Widget", "quantity": 2,
                     "inventory_item_id": "inv-red", "price": "39.99"},
                ],
                "shipping_address": {"name": "Buyer Two", "city": "Ventura", "country": "US"},
            },
        ]
        self.inventory: list[dict] = inventory if inventory is not None else [
            {"inventory_item_id": "inv-blk", "sku": "WIDGET-BLK",
             "location_id": "loc-1", "available": 12},
            {"inventory_item_id": "inv-red", "sku": "WIDGET-RED",
             "location_id": "loc-1", "available": 3},
        ]
        self.writes: list[dict] = []

    def list_orders(self, since: str = "", status: str = "any") -> list[dict]:
        out = self.orders
        if since:
            out = [o for o in out if o.get("created_at", "") > since]
        return list(out)

    def get_inventory_levels(self) -> list[dict]:
        return list(self.inventory)

    def update_order_fulfillment_status(
        self, order_id: str, status: str, tracking: Optional[dict] = None
    ) -> dict:
        record = {"op": "fulfillment", "order_id": order_id, "status": status,
                  "tracking": tracking or {}}
        self.writes.append(record)
        for o in self.orders:
            if o["id"] == order_id:
                o["fulfillment_status"] = status
        return {"ok": True, **record}

    def set_inventory_level(
        self, inventory_item_id: str, location_id: str, available: int
    ) -> dict:
        record = {"op": "inventory", "inventory_item_id": inventory_item_id,
                  "location_id": location_id, "available": available}
        self.writes.append(record)
        for lvl in self.inventory:
            if lvl["inventory_item_id"] == inventory_item_id:
                lvl["available"] = available
        return {"ok": True, **record}


# ---------------------------------------------------------------------------
# Real (httpx) — the only place real Shopify network code lives.
# ---------------------------------------------------------------------------

class RealShopifyClient:
    """Live Shopify Admin REST API client. Requires a store domain + shpat_
    token in config. Raises ``ShopifyNotConnectedError`` if absent — never
    silently stubbed."""

    name = "shopify"

    def __init__(self, config: ShopifyConfig):
        self.config = config

    def _require_live(self) -> None:
        if not self.config.is_live_ready:
            raise ShopifyNotConnectedError(
                "Shopify not connected. Missing: "
                + ", ".join(self.config.missing_for_live())
            )

    def _base_url(self) -> str:
        domain = self.config.store_domain
        if not domain.endswith(".myshopify.com") and "." not in domain:
            domain = f"{domain}.myshopify.com"
        return f"https://{domain}/admin/api/{self.config.api_version}"

    def _client(self):
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - requires httpx
            raise ShopifyError("httpx not installed; run setup.sh") from exc
        return httpx.Client(
            headers={
                "X-Shopify-Access-Token": self.config.access_token,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def list_orders(self, since: str = "", status: str = "any") -> list[dict]:
        self._require_live()
        params = {"status": status, "limit": 100}
        if since:
            params["created_at_min"] = since
        with self._client() as c:
            resp = c.get(f"{self._base_url()}/orders.json", params=params)
            resp.raise_for_status()
            return resp.json().get("orders", [])

    def get_inventory_levels(self) -> list[dict]:
        self._require_live()
        with self._client() as c:
            resp = c.get(f"{self._base_url()}/inventory_levels.json")
            resp.raise_for_status()
            return resp.json().get("inventory_levels", [])

    def update_order_fulfillment_status(
        self, order_id: str, status: str, tracking: Optional[dict] = None
    ) -> dict:
        self._require_live()
        body = {"fulfillment": {"notify_customer": True}}
        if tracking:
            body["fulfillment"].update(tracking)
        with self._client() as c:
            resp = c.post(
                f"{self._base_url()}/orders/{order_id}/fulfillments.json", json=body
            )
            resp.raise_for_status()
            return {"ok": True, "response": resp.json()}

    def set_inventory_level(
        self, inventory_item_id: str, location_id: str, available: int
    ) -> dict:
        self._require_live()
        body = {
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": available,
        }
        with self._client() as c:
            resp = c.post(f"{self._base_url()}/inventory_levels/set.json", json=body)
            resp.raise_for_status()
            return {"ok": True, "response": resp.json()}


def build_shopify_client(config: ShopifyConfig, force: Optional[str] = None) -> ShopifyClient:
    """Factory. Uses the real client only when live-ready (or forced 'real');
    otherwise the offline stub. ``force`` = 'stub' | 'real' overrides."""
    import os

    choice = (force or os.environ.get("EVA_SHOPIFY_CLIENT", "")).lower()
    if choice == "stub":
        return StubShopifyClient()
    if choice == "real" or config.is_live_ready:
        return RealShopifyClient(config)
    return StubShopifyClient()
