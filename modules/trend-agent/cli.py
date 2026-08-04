"""
EVA Trend Agent — CLI
=======================
Offline entrypoint for both trend-agent modes, matching the deal-scout /
monetizing-agent cli.py convention. No server needed for scheduled runs.

Usage:
    python3 cli.py thesis cases/basic_needs_2026.json
    python3 cli.py app-scan cases/app_scan_2026-07.json
    python3 cli.py competitor-scan                  # diff this month's snapshot
    python3 cli.py competitor-scan --fetch          # fetch it first, then diff
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from agent import TrendAgent
from models import ThesisRunInput
from app_models import AppScanRunInput
from competitor_models import CompetitorScanRunInput
from competitor_scan_engine import CASES_DIR


def cmd_thesis(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    inp = ThesisRunInput(**data)
    agent = TrendAgent()
    result = agent.run_thesis(inp)
    print(result.model_dump_json(indent=2))


def cmd_app_scan(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    inp = AppScanRunInput(**data)
    agent = TrendAgent()
    result = agent.run_app_scan(inp)
    print(result.model_dump_json(indent=2))
    print(
        f"\n[trend-agent] app-scan '{result.run_label}': "
        f"{result.total_second_look_apps}/{result.total_apps_scanned} apps worth a second look. "
        f"Top picks: {', '.join(p.name for p in result.top_priority_picks[:5])}",
        file=sys.stderr,
    )
    for f in result.flags:
        print(f"[trend-agent] FLAG: {f}", file=sys.stderr)


def cmd_competitor_scan(case_file: str | None, do_fetch: bool, cases_dir: str = CASES_DIR) -> int:
    """Diff this month's directory snapshot against the previous month's.

    ``--fetch`` performs the HTTP fetch first; a bare invocation diffs the
    snapshot already on disk (so run_competitor_scan.sh can fetch once and
    then diff, rather than fetching twice).
    """
    if do_fetch:
        import competitor_fetch

        rc = competitor_fetch.main(["--cases-dir", cases_dir])
        if rc != 0:
            return rc

    if case_file is None:
        from competitor_fetch import current_scan_month

        case_file = os.path.join(cases_dir, f"competitor_scan_{current_scan_month()}.json")

    if not os.path.exists(case_file):
        print(
            f"[trend-agent] no snapshot at {case_file}. "
            f"Run 'python3 cli.py competitor-scan --fetch' to fetch it first.",
            file=sys.stderr,
        )
        return 1

    with open(case_file, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    inp = CompetitorScanRunInput(**data)
    agent = TrendAgent()
    result = agent.run_competitor_scan(inp, cases_dir=cases_dir)

    payload = result.model_dump_json(indent=2)
    print(payload)

    result_path = os.path.join(cases_dir, f"competitor_scan_{result.scan_date}_result.json")
    with open(result_path, "w", encoding="utf-8") as fh:
        fh.write(payload + "\n")

    print(
        f"\n[trend-agent] competitor-scan {result.scan_date}: {result.verdict} "
        f"({len(result.new_entrants)} new of {result.total_entries} entries, "
        f"diffed against {result.previous_scan_date or 'nothing — baseline run'}). "
        f"Result written to {result_path}",
        file=sys.stderr,
    )
    for f in result.flags:
        print(f"[trend-agent] FLAG: {f}", file=sys.stderr)
    if result.verdict == "ALERT":
        names = ", ".join(e.name for e in result.new_entrants)
        print(
            f"ALERT: new direct competitor(s) in EVA's buy-side deal-sourcing niche "
            f"({result.scan_date}): {names}"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Trend Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_thesis = sub.add_parser("thesis", help="Run the sector-durability thesis model on a case file")
    p_thesis.add_argument("case_file")

    p_app_scan = sub.add_parser("app-scan", help="Run the App Category Scan on a case file")
    p_app_scan.add_argument("case_file")

    p_competitor = sub.add_parser(
        "competitor-scan", help="Diff this month's competitor-directory snapshot against last month's"
    )
    p_competitor.add_argument(
        "case_file", nargs="?", default=None, help="Snapshot to diff (default: this month's)"
    )
    p_competitor.add_argument(
        "--fetch", action="store_true", help="Fetch this month's snapshot before diffing"
    )
    p_competitor.add_argument("--cases-dir", default=CASES_DIR)

    args = parser.parse_args()
    if args.command == "thesis":
        cmd_thesis(args.case_file)
    elif args.command == "app-scan":
        cmd_app_scan(args.case_file)
    elif args.command == "competitor-scan":
        sys.exit(cmd_competitor_scan(args.case_file, args.fetch, cases_dir=args.cases_dir))


if __name__ == "__main__":
    main()
