"""
EVA Channels — terminal-first CLI.

Lets the founder drive multi-platform publishing from the terminal
(voice/terminal-first workflow). Mirrors spec section 6:

  channels create --platform reddit --title "..." --body "..." [--subreddit r/...]
  channels list [--status draft|approved|posted|failed] [--platform reddit|substack]
  channels approve <id>
  channels publish <id>                 (gated; only approved items post)
  channels config set reddit --subreddit r/Entrepreneur --client-id-env REDDIT_CLIENT_ID
  channels config set substack --publication-url https://....substack.com
  channels config get <platform>
  channels tick                         (publish next due; safe from cron)
  channels ledger [--export csv]
  channels memory set <key> <value> | get <key> | list

Run:  python cli.py <command> ...   (or wire under `eva channels ...`)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import ChannelsService, ChannelError, NotFoundError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_create(svc: ChannelsService, args) -> None:
    payload_json = "{}"
    if args.subreddit:
        payload_json = json.dumps({"subreddit": args.subreddit})
    item = svc.create_item({
        "platform": args.platform,
        "title": args.title,
        "body": args.body or "",
        "payload_json": payload_json,
        "scheduled_at": args.scheduled_at or "",
        "actor": "cli",
    })
    _print(item)


def cmd_list(svc: ChannelsService, args) -> None:
    _print(svc.list_items(status=args.status, platform=args.platform))


def cmd_approve(svc: ChannelsService, args) -> None:
    _print(svc.approve_item(args.id, actor="cli"))


def cmd_publish(svc: ChannelsService, args) -> None:
    _print(svc.publish_item(args.id, actor="cli"))


def cmd_tick(svc: ChannelsService, args) -> None:
    _print(svc.tick(actor="cli"))


def cmd_config(svc: ChannelsService, args) -> None:
    if args.config_cmd == "get":
        _print(svc.get_config(args.platform))
        return
    values = {}
    if args.subreddit is not None:
        values["subreddit"] = args.subreddit
    if args.client_id_env is not None:
        values["client_id_env"] = args.client_id_env
    if args.user_agent is not None:
        values["user_agent"] = args.user_agent
    if args.publication_url is not None:
        values["publication_url"] = args.publication_url
    if args.session_env is not None:
        values["session_env"] = args.session_env
    _print(svc.update_config(args.platform, values, actor="cli"))


def cmd_schedule(svc: ChannelsService, args) -> None:
    fields = {}
    if args.cadence_days is not None:
        fields["cadence_days"] = args.cadence_days
    if args.next_due is not None:
        fields["next_due"] = args.next_due
    if fields:
        _print(svc.update_schedule(fields, actor="cli"))
    else:
        _print(svc.get_schedule())


def cmd_ledger(svc: ChannelsService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


def cmd_memory(svc: ChannelsService, args) -> None:
    if args.memory_cmd == "set":
        _print(svc.set_memory(args.key, args.value, source="cli"))
    elif args.memory_cmd == "get":
        _print(svc.get_memory(args.key))
    else:
        _print(svc.all_memory())


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="channels", description="EVA Channels CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a draft item")
    p_create.add_argument("--platform", required=True, choices=["reddit", "substack"])
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--body", default="")
    p_create.add_argument("--subreddit", help="Reddit subreddit, e.g. r/Entrepreneur")
    p_create.add_argument("--scheduled-at", dest="scheduled_at")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="List items")
    p_list.add_argument("--status", choices=["draft", "approved", "posted", "failed"])
    p_list.add_argument("--platform", choices=["reddit", "substack"])
    p_list.set_defaults(func=cmd_list)

    p_approve = sub.add_parser("approve", help="Approve an item for publishing")
    p_approve.add_argument("id")
    p_approve.set_defaults(func=cmd_approve)

    p_publish = sub.add_parser("publish", help="Publish an item (only approved posts)")
    p_publish.add_argument("id")
    p_publish.set_defaults(func=cmd_publish)

    p_tick = sub.add_parser("tick", help="Publish next approved-due item (safe for cron)")
    p_tick.set_defaults(func=cmd_tick)

    p_config = sub.add_parser("config", help="Get/set per-platform config")
    config_sub = p_config.add_subparsers(dest="config_cmd", required=True)
    c_get = config_sub.add_parser("get", help="Print a platform config")
    c_get.add_argument("platform", choices=["reddit", "substack"])
    c_get.set_defaults(func=cmd_config)
    c_set = config_sub.add_parser("set", help="Update a platform config")
    c_set.add_argument("platform", choices=["reddit", "substack"])
    c_set.add_argument("--subreddit")
    c_set.add_argument("--client-id-env", dest="client_id_env")
    c_set.add_argument("--user-agent", dest="user_agent")
    c_set.add_argument("--publication-url", dest="publication_url")
    c_set.add_argument("--session-env", dest="session_env")
    c_set.set_defaults(func=cmd_config)

    p_schedule = sub.add_parser("schedule", help="View or update the publish schedule")
    p_schedule.add_argument("--cadence-days", dest="cadence_days", type=int)
    p_schedule.add_argument("--next-due", dest="next_due")
    p_schedule.set_defaults(func=cmd_schedule)

    p_ledger = sub.add_parser("ledger", help="Query/export the change ledger")
    p_ledger.add_argument("--export", choices=["csv", "json"])
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    p_memory = sub.add_parser("memory", help="Read/write the agent memory table")
    memory_sub = p_memory.add_subparsers(dest="memory_cmd", required=True)
    m_set = memory_sub.add_parser("set")
    m_set.add_argument("key")
    m_set.add_argument("value")
    m_set.set_defaults(func=cmd_memory)
    m_get = memory_sub.add_parser("get")
    m_get.add_argument("key")
    m_get.set_defaults(func=cmd_memory)
    m_list = memory_sub.add_parser("list")
    m_list.set_defaults(func=cmd_memory)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = ChannelsService()
    try:
        args.func(svc, args)
        return 0
    except (ChannelError, NotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
