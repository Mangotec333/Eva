"""
EVA Postcards — terminal-first CLI.

Lets the founder drive the quote-card queue from the terminal (voice/terminal-
first workflow). Mirrors spec section 6:

  postcards seed
  postcards list [--status draft|approved|posted]
  postcards approve <id>
  postcards render <id>
  postcards schedule --cadence-days 3 --start 2026-07-22
  postcards tick                      (post next due; safe to call from cron)
  postcards ledger [--export csv]

Run:  python cli.py <command> ...   (or wire under `eva postcards ...`)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import NotFoundError, PostcardError, PostcardsService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_seed(svc: PostcardsService, args) -> None:
    result = svc.seed(actor="cli")
    _print({"created": len(result["created"]), "skipped": len(result["skipped"])})


def cmd_list(svc: PostcardsService, args) -> None:
    _print(svc.list_cards(status=args.status))


def cmd_approve(svc: PostcardsService, args) -> None:
    _print(svc.approve_card(args.id, actor="cli"))


def cmd_render(svc: PostcardsService, args) -> None:
    _print(svc.render(args.id, actor="cli"))


def cmd_schedule(svc: PostcardsService, args) -> None:
    fields = {}
    if args.cadence_days is not None:
        fields["cadence_days"] = args.cadence_days
    if args.start is not None:
        fields["start_date"] = args.start
        # Re-point next_due to the new start unless already advanced past it.
        fields["next_due"] = args.start
    if fields:
        _print(svc.update_schedule(fields, actor="cli"))
    else:
        _print(svc.get_schedule())


def cmd_tick(svc: PostcardsService, args) -> None:
    _print(svc.tick(actor="cli"))


def cmd_ledger(svc: PostcardsService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="postcards", description="EVA Postcards CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Load the 8 authored quote-cards (idempotent)")
    p_seed.set_defaults(func=cmd_seed)

    p_list = sub.add_parser("list", help="List cards")
    p_list.add_argument("--status", choices=["draft", "approved", "posted", "failed"])
    p_list.set_defaults(func=cmd_list)

    p_approve = sub.add_parser("approve", help="Approve a card for scheduling")
    p_approve.add_argument("id")
    p_approve.set_defaults(func=cmd_approve)

    p_render = sub.add_parser("render", help="Render a card's PNG")
    p_render.add_argument("id")
    p_render.set_defaults(func=cmd_render)

    p_schedule = sub.add_parser("schedule", help="View or update the publish schedule")
    p_schedule.add_argument("--cadence-days", dest="cadence_days", type=int)
    p_schedule.add_argument("--start", help="start_date, e.g. 2026-07-22")
    p_schedule.set_defaults(func=cmd_schedule)

    p_tick = sub.add_parser("tick", help="Post next due approved card (safe for cron)")
    p_tick.set_defaults(func=cmd_tick)

    p_ledger = sub.add_parser("ledger", help="Query/export the publish ledger")
    p_ledger.add_argument("--export", choices=["csv", "json"])
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = PostcardsService()
    try:
        args.func(svc, args)
        return 0
    except (PostcardError, NotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
