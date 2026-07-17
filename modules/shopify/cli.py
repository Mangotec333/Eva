"""
EVA Shopify — terminal-first CLI.

Drive the Shopify store from the terminal (voice/terminal-first workflow).
Mirrors the REST surface; both call the same service layer.

  shopify sync [--since ISO] [--status any|open|closed]
  shopify orders [--fulfillment-status ...]
  shopify forward <order_id>            (dropship: forward to supplier)
  shopify fulfill <order_id> [--tracking-number N --company C]   (-> approval)
  shopify inventory
  shopify set-inventory <item_id> <location_id> <available>      (-> approval)
  shopify approvals [--status pending_approval|approved|executed|rejected|failed]
  shopify approve <approval_id> [--by NAME]
  shopify reject  <approval_id> [--by NAME]
  shopify ledger [--export csv|json] [--event-type ...]

Run:  python cli.py <command> ...   (or wire under `eva shopify ...`)

Live writes (fulfill / set-inventory) are recorded as pending approvals and are
only performed against the real store after `shopify approve <id>`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import NotFoundError, ShopifyService, ShopifyServiceError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_sync(svc: ShopifyService, args) -> None:
    _print(svc.sync_orders(since=args.since or "", status=args.status, actor="cli"))


def cmd_orders(svc: ShopifyService, args) -> None:
    _print(svc.list_orders(fulfillment_status=args.fulfillment_status))


def cmd_forward(svc: ShopifyService, args) -> None:
    _print(svc.forward_order(args.order_id, actor="cli"))


def cmd_fulfill(svc: ShopifyService, args) -> None:
    payload = {
        "status": args.status,
        "tracking_number": args.tracking_number or "",
        "tracking_company": args.company or "",
        "tracking_url": args.tracking_url or "",
    }
    _print(svc.request_fulfillment(args.order_id, payload, actor="cli"))


def cmd_inventory(svc: ShopifyService, args) -> None:
    _print(svc.get_inventory())


def cmd_set_inventory(svc: ShopifyService, args) -> None:
    _print(svc.request_set_inventory(
        args.item_id, args.location_id, args.available, actor="cli"))


def cmd_approvals(svc: ShopifyService, args) -> None:
    _print(svc.list_approvals(status=args.status))


def cmd_approve(svc: ShopifyService, args) -> None:
    _print(svc.approve(args.approval_id, approved_by=args.by))


def cmd_reject(svc: ShopifyService, args) -> None:
    _print(svc.reject(args.approval_id, approved_by=args.by))


def cmd_ledger(svc: ShopifyService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shopify", description="EVA Shopify CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync", help="Pull recent orders into local storage")
    p.add_argument("--since", help="ISO timestamp lower bound")
    p.add_argument("--status", default="any", choices=["any", "open", "closed", "cancelled"])
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("orders", help="List synced orders")
    p.add_argument("--fulfillment-status", dest="fulfillment_status")
    p.set_defaults(func=cmd_orders)

    p = sub.add_parser("forward", help="Forward an order to the supplier (dropship)")
    p.add_argument("order_id")
    p.set_defaults(func=cmd_forward)

    p = sub.add_parser("fulfill", help="Request a live fulfillment update (-> approval)")
    p.add_argument("order_id")
    p.add_argument("--status", default="fulfilled")
    p.add_argument("--tracking-number", dest="tracking_number")
    p.add_argument("--company", dest="company")
    p.add_argument("--tracking-url", dest="tracking_url")
    p.set_defaults(func=cmd_fulfill)

    p = sub.add_parser("inventory", help="Read current inventory levels")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("set-inventory", help="Request a live inventory change (-> approval)")
    p.add_argument("item_id")
    p.add_argument("location_id")
    p.add_argument("available", type=int)
    p.set_defaults(func=cmd_set_inventory)

    p = sub.add_parser("approvals", help="List pending/decided approvals")
    p.add_argument("--status", choices=[
        "pending_approval", "approved", "executed", "rejected", "failed"])
    p.set_defaults(func=cmd_approvals)

    p = sub.add_parser("approve", help="Approve + execute a live write")
    p.add_argument("approval_id")
    p.add_argument("--by", default="founder")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="Reject a pending approval")
    p.add_argument("approval_id")
    p.add_argument("--by", default="founder")
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("ledger", help="Query/export the append-only ledger")
    p.add_argument("--export", choices=["csv", "json"])
    p.add_argument("--event-type", dest="event_type")
    p.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = ShopifyService()
    try:
        args.func(svc, args)
        return 0
    except (ShopifyServiceError, NotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
