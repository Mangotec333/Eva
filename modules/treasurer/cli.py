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
import sys

import bills as bills_engine
import budgeting
from ingest import run_ingestion
from providers import SimpleFINProvider, suggest_account_sides, write_account_map
from store import open_side


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _list_raw_accounts(provider: str) -> list[dict]:
    """Fetch every linked account (unfiltered) so the user can map sides.

    No side, no store, no DB write — this is purely for inspection while
    hand-building ``account_sides.json``.
    """
    if provider != "simplefin":
        raise ValueError(f"accounts inspection only supports simplefin, not {provider!r}")
    raw = SimpleFINProvider().fetch_all()
    return [
        {
            "external_id": a["external_id"],
            "institution": a["institution"],
            "name": a["name"],
            "account_type": a["account_type"],
        }
        for a in raw["accounts"]
    ]


_SUGGEST_WARNING = (
    "SUGGESTED mapping based on account/institution name — review before "
    "trusting it, then edit account_sides.json directly to fix any misclassified "
    "accounts. This file is not regenerated automatically on future runs, so "
    "manual corrections persist."
)


def _suggest_sides(provider: str) -> dict:
    """Classify raw accounts into a suggested side map and write it to disk.

    Convenience bootstrap for ``account_sides.json`` — never a replacement for a
    reviewed file. Refuses to overwrite an existing map (see ``write_account_map``).
    Returns the mapping so callers/tests can inspect it.
    """
    if provider != "simplefin":
        raise ValueError(f"accounts inspection only supports simplefin, not {provider!r}")
    raw = SimpleFINProvider().fetch_all()
    mapping = suggest_account_sides(raw["accounts"])
    path = write_account_map(mapping)  # raises if a map already exists
    print(_SUGGEST_WARNING, file=sys.stderr)
    print(f"Wrote suggestions to {path}", file=sys.stderr)
    return mapping


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

    # No --side: inspect raw linked accounts so the user can build the map file.
    p_acct = sub.add_parser(
        "accounts",
        help="list raw linked accounts from a provider (no side, no DB write)")
    p_acct.add_argument("--provider", default="simplefin", choices=["simplefin"])
    p_acct.add_argument(
        "--suggest-sides", action="store_true",
        help="guess personal/business per account and write a suggested "
             "account_sides.json (review before ingesting; refuses to overwrite)")

    args = parser.parse_args(argv)

    if args.cmd == "accounts":
        if args.suggest_sides:
            _print(_suggest_sides(args.provider))
        else:
            _print(_list_raw_accounts(args.provider))
        return

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
