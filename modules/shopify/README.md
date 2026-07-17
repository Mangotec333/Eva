# EVA Shopify

Order sync + inventory + **dropshipping fulfillment** for Vineet's Shopify store.

This module was auth-only before; it now has a full agent surface built to the
EVA Architecture Directive:

- **Transport behind a Protocol + offline Stub** — all Shopify Admin API I/O
  lives behind `ShopifyClient`, with a `StubShopifyClient` (canned data, no
  network) so the service and its tests run fully offline with **zero
  credentials**.
- **Approval gate on every irreversible live write** — updating an order's
  fulfillment status or setting an inventory level are irreversible against a
  live store, so they are **never executed directly**. They are recorded as
  `pending_approval` and only performed once explicitly approved (canonical
  `pending_approval → approved → executed/rejected/failed` lifecycle).
- **Own SQLite** with a per-agent `memory` table and an **append-only `ledger`**
  (immutable via `BEFORE UPDATE`/`BEFORE DELETE` triggers).
- **Config-driven, nothing hardcoded** — store domain, API token, product SKUs,
  and the fulfillment/supplier target all come from env or
  `~/.eva/channels_config.json`. No store or vendor is guessed.
- **Fails safe** — an unwired live client never fakes success; it reports
  `not_connected`.

Port: **8788**.

---

## What you must supply to go live

Until you provide these, the module runs in **offline stub mode**: reads return
canned data and approved live writes are marked `failed` with a clear
`not connected` error (never silently faked).

| Prerequisite | Env var | `channels_config.json` key | Notes |
|---|---|---|---|
| **Store domain** | `EVA_SHOPIFY_STORE_DOMAIN` | `store_url` / `shop` | e.g. `your-store.myshopify.com` |
| **Admin API token** | `EVA_SHOPIFY_TOKEN` | `admin_api_token` / `access_token` | must be an `shpat_...` token |
| API version | `EVA_SHOPIFY_API_VERSION` | `api_version` | defaults to `2024-07` |
| Product scope (optional) | `EVA_SHOPIFY_PRODUCT_SKUS` | `product_skus` | comma-separated in env; list in JSON |
| **Fulfillment mode** | `EVA_SHOPIFY_FULFILLMENT_MODE` | `fulfillment_mode` | `stub` \| `webhook` \| `email` |
| Supplier webhook URL | `EVA_SHOPIFY_FULFILLMENT_WEBHOOK` | `fulfillment_webhook_url` | required if mode = `webhook` |
| Supplier email | `EVA_SHOPIFY_FULFILLMENT_EMAIL` | `fulfillment_email` | for mode = `email` (transport is a hook — see below) |

Required Admin API scopes (already requested by the existing OAuth handler):
`read_orders, write_orders, read_inventory, write_inventory, read_fulfillments,
write_fulfillments` (and `read_products` for SKU scope).

See `channels_config.example.json` for the exact shape. The token is what the
existing `oauth_handler.py` / `shopify_auth.py` install flow writes.

### Dropshipping fulfillment target

For dropshipping, "fulfilling a new order" means **forwarding the order to your
supplier / fulfillment partner**. That partner is specific to your business and
was not provided, so it is entirely config-driven via `fulfillment_mode`:

- `stub` (default) — records what *would* be sent; sends nothing. Good for
  offline runs and tests.
- `webhook` — POSTs the order payload to `fulfillment_webhook_url`.
- `email` — hands the payload to EVA's email transport. **This is a hook only**:
  the email adapter is not wired here, so it reports `not_connected` (and shows
  what it *would* send) rather than faking a send. Wire EVA's email adapter to
  activate it.

---

## Run

```bash
./setup.sh                       # installs deps, starts on :8788
# or
python main.py --port 8788
```

Health: `GET http://localhost:8788/health` — reports `live_ready`, the active
client (`stub`/`shopify`), the fulfillment mode, and `missing_for_live`.

## CLI

```bash
python cli.py sync                          # pull recent orders into local storage
python cli.py orders                        # list synced orders
python cli.py forward <order_id>            # dropship: forward order to supplier
python cli.py fulfill <order_id>            # request live fulfillment update -> approval
python cli.py inventory                     # read inventory levels
python cli.py set-inventory <item> <loc> 42 # request live inventory change -> approval
python cli.py approvals --status pending_approval
python cli.py approve <approval_id>         # approve + execute the live write
python cli.py reject  <approval_id>
python cli.py ledger --export json
```

## API

```
POST /sync                     Pull recent orders into local storage
GET  /orders                   List synced orders (?fulfillment_status=)
GET  /orders/{id}              Get a synced order
POST /orders/{id}/forward      Forward order to supplier (dropship fulfill)
POST /orders/{id}/fulfill      Request live fulfillment update -> approval
GET  /inventory                Read current inventory levels
POST /inventory/set            Request a live inventory change -> approval
GET  /approvals                List approvals (?status=)
GET  /approvals/{id}           Get an approval
POST /approvals/{id}/approve   Approve + execute the live write
POST /approvals/{id}/reject    Reject a pending approval
GET  /memory                   List agent memory
POST /memory                   Set an agent memory key
GET  /ledger                   Query the append-only ledger
GET  /ledger/export            Export the ledger (csv|json)
GET  /health                   Health check
```

## Approval gate — how a live write happens

1. `POST /orders/{id}/fulfill` (or `/inventory/set`) records a
   `pending_approval` row. **No Shopify write happens.**
2. Review with `GET /approvals?status=pending_approval`.
3. `POST /approvals/{id}/approve` marks it `approved`, then performs the single
   live Admin API call and marks it `executed`. If the store isn't connected the
   approval is marked `failed` with the error — nothing is faked.
4. `POST /approvals/{id}/reject` marks it `rejected`; it can never be executed.

Every step is written to the append-only `ledger`.

## Tests

Fully offline (Protocol + Stub, throwaway SQLite, zero network):

```bash
python test_shopify.py     # standalone runner
pytest test_shopify.py     # or via pytest
```

## Data model

- `orders` — synced Shopify orders + local `forwarded` state (idempotent on
  `shopify_order_id`).
- `pending_approvals` — the approval-gate queue for irreversible live writes.
- `memory` — per-agent key/value (Agent Intelligence Layer).
- `ledger` — append-only event trail (immutable via triggers).
