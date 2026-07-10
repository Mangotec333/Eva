"""
EVA State Ledger — terminal-first CLI.

Append to and read the governed state ledger from the terminal:

  eva state add <event_type> [--summary ... --project ... --entity-type ... ]
  eva state today                       today's priorities (blockers/deadlines/traction)
  eva state map                         the Kalpawriksha tree (JSON)
  eva state recent [--limit N]          recent decisions
  eva state open-blockers               standing blockers
  eva state coined-terms                coined terms + traction
  eva state render-map [--html]         regenerate project_map.json (+ index.html)
  eva state seed [--force]              idempotent seed (import map + lost state)

Run:  python cli.py <command> ...   (or wire under `eva state ...`)
Offline by default in the sandbox; set EVA_STATE_OFFLINE=1 to force stubs.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import NotFoundError, StateService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_add(svc: StateService, args) -> None:
    payload = json.loads(args.payload) if args.payload else {}
    evidence = args.evidence.split(",") if args.evidence else None
    event = svc.record(
        event_type=args.event_type, summary=args.summary, actor=args.actor,
        source_surface=args.source, project=args.project, track=args.track,
        entity_type=args.entity_type, entity_id=args.entity_id,
        payload=payload, evidence_urls=evidence, status=args.status,
    )
    _print(event)


def cmd_today(svc: StateService, args) -> None:
    _print(svc.today())


def cmd_map(svc: StateService, args) -> None:
    _print(svc.project_map())


def cmd_recent(svc: StateService, args) -> None:
    _print(svc.recent_decisions(args.limit))


def cmd_open_blockers(svc: StateService, args) -> None:
    _print(svc.open_blockers())


def cmd_coined_terms(svc: StateService, args) -> None:
    _print(svc.coined_terms())


def cmd_render_map(svc: StateService, args) -> None:
    _print(svc.render_map(write_json=True, write_html=args.html, publish=args.publish))


def cmd_seed(svc: StateService, args) -> None:
    import seed
    _print(seed.seed_all(svc.db_path, force=args.force))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eva-state", description="EVA State Ledger CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Append an event to the ledger")
    p_add.add_argument("event_type")
    p_add.add_argument("--summary", default="")
    p_add.add_argument("--actor", default="Vineet")
    p_add.add_argument("--source", default="cli")
    p_add.add_argument("--project", default="")
    p_add.add_argument("--track", default="")
    p_add.add_argument("--entity-type", dest="entity_type", default="")
    p_add.add_argument("--entity-id", dest="entity_id", default="")
    p_add.add_argument("--payload", default="", help="JSON payload string")
    p_add.add_argument("--evidence", default="", help="comma-separated URLs")
    p_add.add_argument("--status", default="open")
    p_add.set_defaults(func=cmd_add)

    p_today = sub.add_parser("today", help="Today's priorities")
    p_today.set_defaults(func=cmd_today)

    p_map = sub.add_parser("map", help="Kalpawriksha tree (JSON)")
    p_map.set_defaults(func=cmd_map)

    p_recent = sub.add_parser("recent", help="Recent decisions")
    p_recent.add_argument("--limit", type=int, default=20)
    p_recent.set_defaults(func=cmd_recent)

    p_block = sub.add_parser("open-blockers", help="Standing blockers")
    p_block.set_defaults(func=cmd_open_blockers)

    p_coin = sub.add_parser("coined-terms", help="Coined terms + traction")
    p_coin.set_defaults(func=cmd_coined_terms)

    p_render = sub.add_parser("render-map", help="Regenerate project_map.json")
    p_render.add_argument("--html", action="store_true", help="also write index.html")
    p_render.add_argument("--publish", action="store_true", help="publish (gated) after render")
    p_render.set_defaults(func=cmd_render_map)

    p_seed = sub.add_parser("seed", help="Idempotent seed (import map + lost state)")
    p_seed.add_argument("--force", action="store_true")
    p_seed.set_defaults(func=cmd_seed)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = StateService()
    try:
        args.func(svc, args)
        return 0
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
