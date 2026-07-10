"""
EVA LinkedIn Analytics — terminal-first CLI.

Lets the founder drive analytics sync from the terminal (voice/terminal-first
workflow). Mirrors spec section 6:

  linkedin-analytics sync
  linkedin-analytics posts
  linkedin-analytics snapshots <post_urn>
  linkedin-analytics summary [--days 28]
  linkedin-analytics config set --author-urn urn:li:organization:XXX --window-days 28
  linkedin-analytics ledger [--export csv]
  linkedin-analytics tick

Run:  python cli.py <command> ...   (or wire under `eva linkedin-analytics ...`)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import LinkedInAnalyticsService, NotFoundError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_sync(svc: LinkedInAnalyticsService, args) -> None:
    _print(svc.sync(actor="cli"))


def cmd_tick(svc: LinkedInAnalyticsService, args) -> None:
    _print(svc.tick(actor="cli"))


def cmd_posts(svc: LinkedInAnalyticsService, args) -> None:
    _print(svc.list_posts())


def cmd_snapshots(svc: LinkedInAnalyticsService, args) -> None:
    _print(svc.list_snapshots(args.post_urn))


def cmd_summary(svc: LinkedInAnalyticsService, args) -> None:
    _print(svc.summary(days=args.days))


def cmd_config(svc: LinkedInAnalyticsService, args) -> None:
    if args.config_cmd == "get":
        _print(svc.get_config())
        return
    # set
    fields = {
        "author_urn": args.author_urn,
        "access_token_env": args.access_token_env,
        "sync_window_days": args.window_days,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    _print(svc.set_config(fields, actor="cli"))


def cmd_ledger(svc: LinkedInAnalyticsService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


def cmd_memory(svc: LinkedInAnalyticsService, args) -> None:
    if args.memory_cmd == "set":
        _print(svc.memory_set(args.key, args.value, source="cli"))
    elif args.memory_cmd == "get":
        got = svc.memory_get(args.key)
        _print(got or {})
    else:
        _print(svc.memory_all())


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linkedin-analytics", description="EVA LinkedIn Analytics CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Pull latest analytics (cron-safe)")
    p_sync.set_defaults(func=cmd_sync)

    p_tick = sub.add_parser("tick", help="Sync if due (cron-safe, idempotent)")
    p_tick.set_defaults(func=cmd_tick)

    p_posts = sub.add_parser("posts", help="List posts + latest metrics")
    p_posts.set_defaults(func=cmd_posts)

    p_snap = sub.add_parser("snapshots", help="Time-series for a post")
    p_snap.add_argument("post_urn")
    p_snap.set_defaults(func=cmd_snapshots)

    p_sum = sub.add_parser("summary", help="Totals + top post by impressions")
    p_sum.add_argument("--days", type=int, default=28)
    p_sum.set_defaults(func=cmd_summary)

    p_cfg = sub.add_parser("config", help="Get or set sync config")
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", required=True)
    cfg_sub.add_parser("get", help="Show current config")
    p_cfg_set = cfg_sub.add_parser("set", help="Update config")
    p_cfg_set.add_argument("--author-urn", dest="author_urn")
    p_cfg_set.add_argument("--access-token-env", dest="access_token_env")
    p_cfg_set.add_argument("--window-days", dest="window_days", type=int)
    p_cfg.set_defaults(func=cmd_config)

    p_ledger = sub.add_parser("ledger", help="Query/export the analytics ledger")
    p_ledger.add_argument("--export", choices=["csv", "json"])
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    p_mem = sub.add_parser("memory", help="Read/write agent memory")
    mem_sub = p_mem.add_subparsers(dest="memory_cmd", required=True)
    mem_sub.add_parser("list", help="List all memory")
    p_mem_get = mem_sub.add_parser("get", help="Get a memory value")
    p_mem_get.add_argument("key")
    p_mem_set = mem_sub.add_parser("set", help="Set a memory value")
    p_mem_set.add_argument("key")
    p_mem_set.add_argument("value")
    p_mem.set_defaults(func=cmd_memory)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = LinkedInAnalyticsService()
    try:
        args.func(svc, args)
        return 0
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
