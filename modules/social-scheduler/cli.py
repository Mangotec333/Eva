#!/usr/bin/env python3
"""
EVA Social-Scheduler — CLI mirror of the schedule routes.

Examples:
  python cli.py seed                       # pre-seed day-1 content queue
  python cli.py schedule                   # show queue + fixed ET slots
  python cli.py run                        # one pass (submit due → publish)
  python cli.py sync --window-days 30      # sync engagement metrics
  python cli.py analytics                  # latest per-post snapshot + totals

Offline-safe: set EVA_SOCIAL_SCHEDULER_OFFLINE=1 to use no-op seams (no network,
fires nothing). That is the default posture in the sandbox.
"""

from __future__ import annotations

import argparse
import json

from service import SocialSchedulerService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Social-Scheduler CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_seed = sub.add_parser("seed", help="pre-seed the day-1 content queue")
    p_seed.add_argument("--date", default=None, help="scheduled date YYYY-MM-DD (ET today default)")

    sub.add_parser("schedule", help="show the content queue + ET slots")
    sub.add_parser("run", help="one scheduler pass (submit due → publish approved)")

    p_sync = sub.add_parser("sync", help="sync engagement metrics into the store")
    p_sync.add_argument("--window-days", type=int, default=30)

    sub.add_parser("analytics", help="latest per-post engagement snapshot + totals")

    args = parser.parse_args()
    svc = SocialSchedulerService()

    if args.cmd == "seed":
        _print(svc.seed(scheduled_date=args.date))
    elif args.cmd == "schedule":
        _print(svc.schedule())
    elif args.cmd == "run":
        _print(svc.run())
    elif args.cmd == "sync":
        _print(svc.sync_analytics(window_days=args.window_days))
    elif args.cmd == "analytics":
        _print(svc.analytics())


if __name__ == "__main__":
    main()
