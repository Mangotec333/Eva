"""
Offline test suite for the EVA Shopify module.

Zero network: every test uses the offline ``StubShopifyClient`` and the
``StubNotifier``, backed by a throwaway SQLite file. Runs two ways:

    python test_shopify.py      # standalone runner, prints PASS/FAIL
    pytest test_shopify.py      # if pytest is installed

Covers: order sync (idempotent), inventory read, dropship forwarding, the
approval gate for irreversible live writes (fulfillment + inventory), fail-safe
behavior when the live client is not connected, and the append-only ledger.
"""

from __future__ import annotations

import os
import tempfile

from config import ShopifyConfig
from database import (
    APPROVAL_EXECUTED,
    APPROVAL_FAILED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    Store,
)
from fulfillment import EmailNotifier, StubNotifier, WebhookNotifier, build_notifier
from service import NotFoundError, ShopifyService, ShopifyServiceError
from shopify_client import (
    RealShopifyClient,
    ShopifyNotConnectedError,
    StubShopifyClient,
    build_shopify_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service(client=None, notifier=None, config=None):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-shopify-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    store = Store(path)
    svc = ShopifyService(
        store=store,
        client=client or StubShopifyClient(),
        notifier=notifier or StubNotifier(),
        config=config or ShopifyConfig(),
    )
    return svc


# ---------------------------------------------------------------------------
# Order sync
# ---------------------------------------------------------------------------

def test_sync_orders_imports_stub_orders():
    svc = _fresh_service()
    result = svc.sync_orders(actor="test")
    assert result["synced"] == 2
    assert result["client"] == "stub"
    orders = svc.list_orders()
    assert len(orders) == 2
    assert {o["shopify_order_id"] for o in orders} == {"5001", "5002"}


def test_sync_is_idempotent():
    svc = _fresh_service()
    svc.sync_orders(actor="test")
    svc.sync_orders(actor="test")
    # Second sync must not duplicate (idempotent on shopify_order_id).
    assert len(svc.list_orders()) == 2


def test_sync_since_filters_orders():
    svc = _fresh_service()
    # 5002 is 2026-07-17, 5001 is 2026-07-16 — filter to just after 5001.
    result = svc.sync_orders(since="2026-07-17T00:00:00Z", actor="test")
    assert result["synced"] == 1
    assert svc.list_orders()[0]["shopify_order_id"] == "5002"


# ---------------------------------------------------------------------------
# Inventory (read)
# ---------------------------------------------------------------------------

def test_inventory_read():
    svc = _fresh_service()
    inv = svc.get_inventory()
    skus = {lvl["sku"] for lvl in inv["inventory"]}
    assert skus == {"WIDGET-BLK", "WIDGET-RED"}


# ---------------------------------------------------------------------------
# Dropship forwarding (no write back to Shopify)
# ---------------------------------------------------------------------------

def test_forward_order_marks_forwarded():
    notifier = StubNotifier()
    svc = _fresh_service(notifier=notifier)
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]
    result = svc.forward_order(order["id"], actor="test")
    assert result["result"]["ok"] is True
    assert len(notifier.sent) == 1
    assert svc.get_order(order["id"])["forwarded"] == 1


def test_email_notifier_never_fakes_send():
    """The email transport is a hook only — it must report not-connected."""
    notifier = EmailNotifier("supplier@example.com")
    svc = _fresh_service(notifier=notifier)
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]
    result = svc.forward_order(order["id"], actor="test")
    assert result["result"]["ok"] is False
    assert "not connected" in result["result"]["error"]
    # Not marked forwarded when the send did not actually happen.
    assert svc.get_order(order["id"])["forwarded"] == 0


# ---------------------------------------------------------------------------
# Approval gate — irreversible live writes
# ---------------------------------------------------------------------------

def test_fulfillment_requires_approval_before_write():
    client = StubShopifyClient()
    svc = _fresh_service(client=client)
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]

    approval = svc.request_fulfillment(
        order["id"], {"status": "fulfilled"}, actor="test")
    assert approval["status"] == APPROVAL_PENDING
    # Nothing written to the (stub) store yet.
    assert client.writes == []


def test_approve_executes_the_live_write():
    client = StubShopifyClient()
    svc = _fresh_service(client=client)
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]

    approval = svc.request_fulfillment(
        order["id"], {"status": "fulfilled"}, actor="test")
    executed = svc.approve(approval["id"], approved_by="founder")

    assert executed["status"] == APPROVAL_EXECUTED
    assert len(client.writes) == 1
    assert client.writes[0]["op"] == "fulfillment"
    assert client.writes[0]["order_id"] == order["shopify_order_id"]


def test_reject_blocks_the_write():
    client = StubShopifyClient()
    svc = _fresh_service(client=client)
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]

    approval = svc.request_fulfillment(order["id"], {"status": "fulfilled"}, actor="test")
    rejected = svc.reject(approval["id"], approved_by="founder")
    assert rejected["status"] == APPROVAL_REJECTED
    assert client.writes == []
    # A rejected approval cannot then be approved.
    try:
        svc.approve(approval["id"])
        assert False, "approving a rejected approval must raise"
    except ShopifyServiceError as exc:
        assert exc.code == "not_pending"


def test_inventory_change_is_approval_gated():
    client = StubShopifyClient()
    svc = _fresh_service(client=client)
    approval = svc.request_set_inventory("inv-blk", "loc-1", 99, actor="test")
    assert approval["status"] == APPROVAL_PENDING
    assert client.writes == []

    svc.approve(approval["id"], approved_by="founder")
    assert len(client.writes) == 1
    assert client.writes[0]["op"] == "inventory"
    assert client.writes[0]["available"] == 99


def test_approve_fails_safe_when_not_connected():
    """Approving with an unwired real client marks the approval failed and never
    fakes success."""
    real = RealShopifyClient(ShopifyConfig())  # no domain/token -> not live-ready
    svc = _fresh_service(client=real)
    approval = svc.request_set_inventory("inv-blk", "loc-1", 5, actor="test")
    result = svc.approve(approval["id"], approved_by="founder")
    assert result["status"] == APPROVAL_FAILED
    assert result["result"]["ok"] is False
    assert "not connected" in result["result"]["error"].lower()


# ---------------------------------------------------------------------------
# Ledger (append-only)
# ---------------------------------------------------------------------------

def test_ledger_records_sync_and_approval_events():
    svc = _fresh_service()
    svc.sync_orders(actor="test")
    order = svc.list_orders()[0]
    approval = svc.request_fulfillment(order["id"], {"status": "fulfilled"}, actor="test")
    svc.approve(approval["id"], approved_by="founder")

    events = {e["event_type"] for e in svc.query_ledger()}
    assert "orders_synced" in events
    assert "approval_requested" in events
    assert "approval_approved" in events
    assert "approval_executed" in events


def test_ledger_is_append_only():
    svc = _fresh_service()
    svc.sync_orders(actor="test")
    rows = svc.query_ledger()
    assert rows
    row_id = rows[0]["id"]

    conn = svc.store._connect()
    try:
        raised_update = False
        try:
            conn.execute("UPDATE ledger SET actor = 'tamper' WHERE id = ?", (row_id,))
            conn.commit()
        except Exception:
            raised_update = True
        assert raised_update, "ledger UPDATE must be blocked"

        raised_delete = False
        try:
            conn.execute("DELETE FROM ledger WHERE id = ?", (row_id,))
            conn.commit()
        except Exception:
            raised_delete = True
        assert raised_delete, "ledger DELETE must be blocked"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Client / notifier factories + not-connected guards
# ---------------------------------------------------------------------------

def test_real_client_raises_when_not_connected():
    real = RealShopifyClient(ShopifyConfig())
    for call in (
        lambda: real.list_orders(),
        lambda: real.get_inventory_levels(),
        lambda: real.update_order_fulfillment_status("1", "fulfilled"),
        lambda: real.set_inventory_level("i", "l", 1),
    ):
        try:
            call()
            assert False, "expected ShopifyNotConnectedError"
        except ShopifyNotConnectedError:
            pass


def test_build_client_defaults_to_stub_without_credentials():
    client = build_shopify_client(ShopifyConfig())
    assert client.name == "stub"


def test_build_client_uses_real_when_live_ready():
    # conftest sets EVA_SHOPIFY_CLIENT=stub as a global network safety net; clear
    # it here to verify a live-ready config alone selects the real client.
    prior = os.environ.pop("EVA_SHOPIFY_CLIENT", None)
    try:
        cfg = ShopifyConfig(store_domain="x.myshopify.com", access_token="shpat_abc")
        client = build_shopify_client(cfg)
        assert client.name == "shopify"
    finally:
        if prior is not None:
            os.environ["EVA_SHOPIFY_CLIENT"] = prior


def test_build_notifier_by_mode():
    assert build_notifier(ShopifyConfig(fulfillment_mode="stub")).name == "stub"
    assert isinstance(
        build_notifier(ShopifyConfig(fulfillment_mode="webhook",
                                     fulfillment_webhook_url="https://x")),
        WebhookNotifier,
    )
    assert isinstance(
        build_notifier(ShopifyConfig(fulfillment_mode="email",
                                     fulfillment_email="s@x.com")),
        EmailNotifier,
    )


def test_get_order_not_found_raises():
    svc = _fresh_service()
    try:
        svc.get_order("does-not-exist")
        assert False, "expected NotFoundError"
    except NotFoundError:
        pass


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    passed, failed = 0, 0
    for test in _all_tests():
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
