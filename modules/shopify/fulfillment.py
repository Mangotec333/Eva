"""
EVA Shopify — dropshipping fulfillment notifier (config-driven, pluggable).

For dropshipping, "fulfilling" a new order means forwarding the order details to
a supplier / fulfillment partner. The partner is user-specific and was not
provided, so the target is entirely config-driven behind a ``FulfillmentNotifier``
Protocol:

  * ``StubNotifier``    — offline, records what would be sent. Default + tests.
  * ``WebhookNotifier`` — POSTs the order payload to a configured supplier URL.
  * ``EmailNotifier``   — hands the payload to EVA's email transport (hook only;
                          reports ``not_connected`` until wired, never fakes).

Selected by ``config.fulfillment_mode`` (stub | webhook | email). Missing target
fails safe (``ok=False`` with a clear error) rather than silently dropping.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from config import ShopifyConfig


@runtime_checkable
class FulfillmentNotifier(Protocol):
    name: str

    def notify(self, order: dict) -> dict: ...


def build_order_payload(order: dict) -> dict:
    """The supplier-facing payload for a dropship order (transport-agnostic)."""
    return {
        "order_id": order.get("id"),
        "order_name": order.get("name"),
        "email": order.get("email"),
        "shipping_address": order.get("shipping_address", {}),
        "line_items": [
            {
                "sku": li.get("sku"),
                "title": li.get("title"),
                "quantity": li.get("quantity"),
            }
            for li in order.get("line_items", [])
        ],
    }


class StubNotifier:
    """Offline notifier: records the payload, sends nothing. No network."""

    name = "stub"

    def __init__(self):
        self.sent: list[dict] = []

    def notify(self, order: dict) -> dict:
        payload = build_order_payload(order)
        self.sent.append(payload)
        return {"ok": True, "mode": self.name, "forwarded": payload}


class WebhookNotifier:
    """POSTs the order payload to a configured supplier webhook URL."""

    name = "webhook"

    def __init__(self, url: str):
        self.url = url

    def notify(self, order: dict) -> dict:
        if not self.url:
            return {"ok": False, "mode": self.name,
                    "error": "no fulfillment_webhook_url configured"}
        payload = build_order_payload(order)
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            return {"ok": False, "mode": self.name, "error": f"httpx missing: {exc}"}
        try:
            with httpx.Client(timeout=30.0) as c:
                resp = c.post(self.url, json=payload)
                resp.raise_for_status()
            return {"ok": True, "mode": self.name, "forwarded": payload,
                    "status_code": resp.status_code}
        except Exception as exc:  # noqa: BLE001 - fail safe to caller
            return {"ok": False, "mode": self.name, "error": str(exc)}


class EmailNotifier:
    """Emails the order to a supplier address via EVA's email transport.

    Hook only: EVA's email transport is not wired here, so this reports
    ``not_connected`` (never fakes a send) until connected."""

    name = "email"

    def __init__(self, email: str):
        self.email = email

    def notify(self, order: dict) -> dict:
        if not self.email:
            return {"ok": False, "mode": self.name,
                    "error": "no fulfillment_email configured"}
        return {
            "ok": False,
            "mode": self.name,
            "error": "email fulfillment transport not connected — wire EVA email "
                     "adapter to send to " + self.email,
            "would_send_to": self.email,
            "payload": build_order_payload(order),
        }


def build_notifier(config: ShopifyConfig) -> FulfillmentNotifier:
    """Factory keyed on config.fulfillment_mode."""
    mode = (config.fulfillment_mode or "stub").lower()
    if mode == "webhook":
        return WebhookNotifier(config.fulfillment_webhook_url)
    if mode == "email":
        return EmailNotifier(config.fulfillment_email)
    return StubNotifier()
