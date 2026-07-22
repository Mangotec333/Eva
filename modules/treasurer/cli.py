#!/usr/bin/env python3
"""
EVA Treasurer — CLI.

Every command takes ``--side personal|business`` and operates on exactly that
side's database. Personal and business data are never combined.

Examples:
  python cli.py ingest  --side personal --provider mock
  python cli.py ingest  --side business --provider csv --csv-path data/txns.csv
  python cli.py budget  --side personal
  python cli.py budget  --side business --period week
  python cli.py bills   --side personal
  python cli.py utilization --side business --threshold 0.30

Offline-safe: the default provider is ``mock`` (fixture data, no network). The
SimpleFIN provider is only used when explicitly selected and a
``SIMPLEFIN_BRIDGE_URL`` is configured.
"""

from __future__ import annotations

import argparse
import json

import bills as bills_engine
import budgeting
from ingest import run_ingestion
from store import open_side


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _add_side(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--side", required=True, choices=["personal", "business"],
                        help="which ledger to operate on (kept strictly separate)")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="EVA Treasurer finance CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="pull transactions from a provider")
    _add_side(p_ing)
    p_ing.add_argument("--provider", default="mock", choices=["mock", "csv", "simplefin"])
    p_ing.add_argument("--csv-path", default=None)
    p_ing.add_argument("--dry-run", action="store_true")

    p_bud = sub.add_parser("budget", help="spend-vs-income rollup")
    _add_side(p_bud)
    p_bud.add_argument("--period", default=None, choices=list(budgeting.PERIODS))

    p_bills = sub.add_parser("bills", help="list upcoming bills")
    _add_side(p_bills)
    p_bills.add_argument("--within-days", type=int, default=30)

    p_util = sub.add_parser("utilization", help="credit utilization + alerts")
    _add_side(p_util)
    p_util.add_argument("--threshold", type=float, default=0.30)

    args = parser.parse_args(argv)
    store = open_side(args.side)
    try:
        if args.cmd == "ingest":
            _print(run_ingestion(store, provider_name=args.provider,
                                 csv_path=args.csv_path, dry_run=args.dry_run))
        elif args.cmd == "budget":
            if args.period:
                _print(budgeting.rollup(store, args.period))
            else:
                _print(budgeting.all_rollups(store))
        elif args.cmd == "bills":
            _print({"side": args.side,
                    "bills": bills_engine.upcoming_bills(store, args.within_days)})
        elif args.cmd == "utilization":
            _print(bills_engine.utilization_report(store, threshold=args.threshold))
    finally:
        store.close()


if __name__ == "__main__":
    main()
