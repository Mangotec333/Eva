#!/usr/bin/env python3
"""
EVA Diracatron — CLI mirror of the three triage routes.

Examples:
  python cli.py queue                    # show the current ranked queue
  python cli.py run                      # run one triage pass (poll → rank → queue)
  python cli.py dispatch <item_id>       # dispatch a specific queued item
  python cli.py dispatch --goal "..."    # dispatch brain: goal → decide → invoke
  python cli.py digest [--top 10]        # prioritized stack-rank of open doors
  python cli.py registry                 # show the data-driven agent registry
  python cli.py history [--limit 20]     # audit recent dispatch decisions

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

    p_disp = sub.add_parser("dispatch", help="dispatch a queued item, or a goal")
    p_disp.add_argument("item_id", nargs="?", help="queued item id to dispatch")
    p_disp.add_argument("--goal", help="free-form goal for the dispatch brain")

    p_dig = sub.add_parser("digest", help="prioritized stack-rank of open doors")
    p_dig.add_argument("--top", type=int, default=10)
    p_dig.add_argument("--alert", action="store_true", default=False)

    sub.add_parser("registry", help="show the data-driven agent registry")

    p_hist = sub.add_parser("history", help="show recent dispatch decisions")
    p_hist.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    svc = DiracatronService()

    if args.cmd == "queue":
        _print(svc.queue())
    elif args.cmd == "run":
        _print(svc.run_pass())
    elif args.cmd == "dispatch":
        if args.goal:
            _print(svc.dispatch_goal(args.goal))
        elif args.item_id:
            _print(svc.dispatch(args.item_id))
        else:
            parser.error("dispatch needs an item_id or --goal")
    elif args.cmd == "digest":
        _print(svc.digest(top=args.top, alert=args.alert))
    elif args.cmd == "registry":
        _print({"agents": svc.registry.to_catalog()})
    elif args.cmd == "history":
        _print(svc.history(limit=args.limit))


if __name__ == "__main__":
    main()
