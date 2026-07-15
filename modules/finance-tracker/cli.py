#!/usr/bin/env python3
"""
EVA Treasurer — CLI mirror of the finance routes.

Examples:
  python cli.py track --category llm_api --amount-cents 1299 --vendor anthropic
  python cli.py summary --period month
  python cli.py budget                       # caps vs actual
  python cli.py set-budget --category ad_spend --cap-cents 500000
  python cli.py export                        # CSV dump
  python cli.py burn                          # month run-rate projection

Offline-safe: set EVA_TREASURER_OFFLINE=1 to use stubs (no network, fires
nothing). That is the default posture in the sandbox.
"""

from __future__ import annotations

import argparse
import json

from service import TreasurerService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Treasurer finance tracker CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_track = sub.add_parser("track", help="log a spend event")
    p_track.add_argument("--category", required=True)
    p_track.add_argument("--amount-cents", type=int, required=True)
    p_track.add_argument("--vendor", default="")
    p_track.add_argument("--source-agent", default="")
    p_track.add_argument("--note", default="")
    p_track.add_argument("--timestamp", default=None)
    p_track.add_argument("--event-key", default=None)

    p_sum = sub.add_parser("summary", help="spend by category for a period")
    p_sum.add_argument("--period", default="month", choices=["day", "week", "month"])

    p_bud = sub.add_parser("budget", help="budget caps vs actual")
    p_bud.add_argument("--period", default=None, choices=["day", "week", "month"])

    p_set = sub.add_parser("set-budget", help="set/update a category cap")
    p_set.add_argument("--category", required=True)
    p_set.add_argument("--cap-cents", type=int, required=True)
    p_set.add_argument("--period", default="month", choices=["day", "week", "month"])

    sub.add_parser("export", help="CSV dump of all spend events")
    sub.add_parser("burn", help="current-month run-rate projection")
    sub.add_parser("daily-summary", help="log today's spend summary to eva-state")

    args = parser.parse_args()
    svc = TreasurerService()

    if args.cmd == "track":
        _print(svc.track(category=args.category, amount_cents=args.amount_cents,
                         vendor=args.vendor, source_agent=args.source_agent,
                         note=args.note, timestamp=args.timestamp,
                         event_key=args.event_key))
    elif args.cmd == "summary":
        _print(svc.summary(args.period))
    elif args.cmd == "budget":
        _print(svc.budget(args.period))
    elif args.cmd == "set-budget":
        _print(svc.set_budget(category=args.category, cap_cents=args.cap_cents,
                              period=args.period))
    elif args.cmd == "export":
        print(svc.export_csv())
    elif args.cmd == "burn":
        _print(svc.burn())
    elif args.cmd == "daily-summary":
        _print(svc.daily_summary())


if __name__ == "__main__":
    main()
