#!/usr/bin/env python3
"""
EVA Remote-Bridge — CLI mirror of the service routes.

Examples:
  python cli.py instruct "review the acquisition pipeline and flag stalls"
  python cli.py instruct "post the nightly digest" --context '{"channel":"ops"}'
  python cli.py status <instruction_id>      # status of one instruction
  python cli.py list --limit 20              # recent instructions (newest first)
  python cli.py ledger <instruction_id>      # append-only audit trail

``instruct`` runs the full receive → dispatch cycle synchronously here (there is
no background task loop in the CLI), so the printed record already reflects the
dispatch outcome. Offline-safe: set EVA_REMOTE_BRIDGE_OFFLINE=1 to use the stub
dispatch + state clients and touch no network (the sandbox default).
"""

from __future__ import annotations

import argparse
import json

from service import RemoteBridgeService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Remote-Bridge CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ins = sub.add_parser("instruct", help="submit a goal and dispatch it")
    p_ins.add_argument("goal", help="the natural-language instruction")
    p_ins.add_argument("--context", default=None,
                       help="optional JSON context object")

    p_stat = sub.add_parser("status", help="status of one instruction")
    p_stat.add_argument("instruction_id")

    p_list = sub.add_parser("list", help="recent instructions (newest first)")
    p_list.add_argument("--limit", type=int, default=20)

    p_ledg = sub.add_parser("ledger", help="append-only audit trail")
    p_ledg.add_argument("instruction_id")

    args = parser.parse_args()
    svc = RemoteBridgeService()

    if args.cmd == "instruct":
        context = json.loads(args.context) if args.context else None
        record = svc.create_and_ack(args.goal, context)
        svc.run_dispatch(record["id"])
        _print(svc.get(record["id"]))
    elif args.cmd == "status":
        record = svc.get(args.instruction_id)
        _print(record if record else {"error": "instruction not found"})
    elif args.cmd == "list":
        items = svc.list(limit=args.limit)
        _print({"count": len(items), "items": items})
    elif args.cmd == "ledger":
        _print({"instruction_id": args.instruction_id,
                "ledger": svc.ledger(args.instruction_id)})


if __name__ == "__main__":
    main()
