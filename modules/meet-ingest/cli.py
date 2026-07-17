"""
EVA Meet Ingest — terminal-first CLI.

Drives the meeting pipeline from the terminal (matches sibling module style):

  python cli.py poll                 discover new Drive recordings (idempotent)
  python cli.py list [--status ...]  list meetings
  python cli.py show <id>            show one meeting
  python cli.py process <id>         run the pipeline for one meeting
  python cli.py tick                 poll + process all pending (safe for cron)
  python cli.py ledger [--event-type ...]

Defaults to the offline stub transports; set EVA_MEET_DRIVE=real and
EVA_MEET_TRANSCRIBER=whisper (with prerequisites installed) for live use.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import MeetIngestService, NotFoundError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_poll(svc: MeetIngestService, args) -> None:
    result = svc.poll(actor="cli")
    _print({k: result[k] for k in ("found", "created", "skipped", "watermark")})


def cmd_list(svc: MeetIngestService, args) -> None:
    _print(svc.list_meetings(status=args.status))


def cmd_show(svc: MeetIngestService, args) -> None:
    _print(svc.get_meeting(args.id))


def cmd_process(svc: MeetIngestService, args) -> None:
    _print(svc.process(args.id, actor="cli"))


def cmd_tick(svc: MeetIngestService, args) -> None:
    result = svc.tick(actor="cli")
    _print({k: result[k] for k in ("polled", "processed", "done", "failed")})


def cmd_ledger(svc: MeetIngestService, args) -> None:
    _print(svc.query_ledger(event_type=args.event_type))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meet-ingest", description="EVA Meet Ingest CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_poll = sub.add_parser("poll", help="Discover new Drive recordings (idempotent)")
    p_poll.set_defaults(func=cmd_poll)

    p_list = sub.add_parser("list", help="List meetings")
    p_list.add_argument(
        "--status",
        choices=["pending", "downloading", "transcribing", "done", "failed"],
    )
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show a meeting")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_process = sub.add_parser("process", help="Run the pipeline for one meeting")
    p_process.add_argument("id")
    p_process.set_defaults(func=cmd_process)

    p_tick = sub.add_parser("tick", help="Poll + process all pending (safe for cron)")
    p_tick.set_defaults(func=cmd_tick)

    p_ledger = sub.add_parser("ledger", help="Query the append-only ledger")
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = MeetIngestService()
    try:
        args.func(svc, args)
        return 0
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
