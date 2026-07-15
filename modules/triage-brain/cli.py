#!/usr/bin/env python3
"""
EVA Diracatron — CLI mirror of the three triage routes.

Examples:
  python cli.py queue                 # show the current ranked queue
  python cli.py run                   # run one triage pass (poll → rank → queue)
  python cli.py dispatch <item_id>    # dispatch a specific queued item
  python cli.py history [--limit 20]  # audit recent dispatch decisions

Offline-safe: set EVA_DIRACATRON_OFFLINE=1 to use stubs (no network, fires
nothing). That is the default posture in the sandbox.
"""

from __future__ import annotations

import argparse
import json

from service import DiracatronService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Diracatron triage brain CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("queue", help="show the current ranked queue")
    sub.add_parser("run", help="run one triage pass")

    p_disp = sub.add_parser("dispatch", help="dispatch a specific queued item")
    p_disp.add_argument("item_id")

    p_hist = sub.add_parser("history", help="show recent dispatch decisions")
    p_hist.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    svc = DiracatronService()

    if args.cmd == "queue":
        _print(svc.queue())
    elif args.cmd == "run":
        _print(svc.run_pass())
    elif args.cmd == "dispatch":
        _print(svc.dispatch(args.item_id))
    elif args.cmd == "history":
        _print(svc.history(limit=args.limit))


if __name__ == "__main__":
    main()
