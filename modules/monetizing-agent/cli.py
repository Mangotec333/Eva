"""
EVA Monetizing Agent — terminal-first CLI.

Drive the weekly scan and the approval-gated brief from the terminal:

  monetizing scan                       run the weekly revenue-leak scan
  monetizing brief [--id <id>]          show the latest brief (or a specific one)
  monetizing plays [--brief <id>]       list ledger plays
  monetizing approve <brief_id>         APPROVAL GATE — approve a brief's plays
  monetizing execute <brief_id>         execute approved plays (Stub offline)
  monetizing outcome <play_id> <type> <outcome> [--lesson ...]   record follow-up

Run:  python cli.py <command> ...   (or wire under `eva monetizing ...`)
Offline by default in the sandbox; set EVA_MONETIZE_OFFLINE=1 to force stubs.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import MonetizingService, NotFoundError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_scan(svc: MonetizingService, args) -> None:
    result = svc.scan()
    if args.raw:
        _print(result)
    else:
        print(result["brief_text"])
        print(f"\n[brief_id: {result['brief_id']}]  report: {result['report_path']}")


def cmd_brief(svc: MonetizingService, args) -> None:
    brief = svc.get_brief(args.id) if args.id else svc.latest_brief()
    if brief is None:
        print("no briefs yet — run: monetizing scan", file=sys.stderr)
        return
    if args.raw:
        _print(brief)
    else:
        print(brief.get("brief_text") or "(no brief text)")
        print(f"\n[brief_id: {brief['id']}]  status: {brief['status']}")


def cmd_plays(svc: MonetizingService, args) -> None:
    from memory import list_plays
    _print(list_plays(brief_id=args.brief, path=svc.db_path))


def cmd_approve(svc: MonetizingService, args) -> None:
    _print(svc.approve(args.brief_id))


def cmd_execute(svc: MonetizingService, args) -> None:
    _print(svc.execute(args.brief_id))


def cmd_outcome(svc: MonetizingService, args) -> None:
    lid = svc.record_outcome(args.play_id, args.play_type, args.outcome, args.lesson)
    _print({"learning_id": lid})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="monetizing", description="EVA Monetizing Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Run the weekly revenue-leak scan")
    p_scan.add_argument("--raw", action="store_true", help="print full JSON")
    p_scan.set_defaults(func=cmd_scan)

    p_brief = sub.add_parser("brief", help="Show the latest (or a specific) brief")
    p_brief.add_argument("--id", help="brief id (defaults to latest)")
    p_brief.add_argument("--raw", action="store_true")
    p_brief.set_defaults(func=cmd_brief)

    p_plays = sub.add_parser("plays", help="List ledger plays")
    p_plays.add_argument("--brief", help="filter by brief id")
    p_plays.set_defaults(func=cmd_plays)

    p_approve = sub.add_parser("approve", help="Approve a brief's plays (approval gate)")
    p_approve.add_argument("brief_id")
    p_approve.set_defaults(func=cmd_approve)

    p_exec = sub.add_parser("execute", help="Execute approved plays")
    p_exec.add_argument("brief_id")
    p_exec.set_defaults(func=cmd_execute)

    p_out = sub.add_parser("outcome", help="Record a play outcome (follow-up)")
    p_out.add_argument("play_id")
    p_out.add_argument("play_type")
    p_out.add_argument("outcome", help="converted | no_response | declined | dead")
    p_out.add_argument("--lesson", default="")
    p_out.set_defaults(func=cmd_outcome)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = MonetizingService()
    try:
        args.func(svc, args)
        return 0
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
