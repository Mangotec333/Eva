"""
EVA Trend Agent — CLI
=======================
Offline entrypoint for both trend-agent modes, matching the deal-scout /
monetizing-agent cli.py convention. No server needed for scheduled runs.

Usage:
    python3 cli.py thesis cases/basic_needs_2026.json
    python3 cli.py app-scan cases/app_scan_2026-07.json
"""

from __future__ import annotations

import argparse
import json
import sys

from agent import TrendAgent
from models import ThesisRunInput
from app_models import AppScanRunInput


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


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Trend Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_thesis = sub.add_parser("thesis", help="Run the sector-durability thesis model on a case file")
    p_thesis.add_argument("case_file")

    p_app_scan = sub.add_parser("app-scan", help="Run the App Category Scan on a case file")
    p_app_scan.add_argument("case_file")

    args = parser.parse_args()
    if args.command == "thesis":
        cmd_thesis(args.case_file)
    elif args.command == "app-scan":
        cmd_app_scan(args.case_file)


if __name__ == "__main__":
    main()
