#!/usr/bin/env python3
"""
EVA Deployer — CLI mirror of the deployer routes.

Examples:
  python cli.py status                     # current SHA + last check + last result
  python cli.py check                      # one poll → safe self-deploy pass
  python cli.py history --limit 20         # recent deploy passes (newest first)

Offline-safe: set EVA_DEPLOYER_OFFLINE=1 to use no-op seams (no git, no gh, no
restart). That is the default posture in the sandbox.
"""

from __future__ import annotations

import argparse
import json

from service import DeployerService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Deployer CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="current SHA + last check + last result")
    sub.add_parser("check", help="one poll → safe self-deploy pass")

    p_hist = sub.add_parser("history", help="recent deploy passes (newest first)")
    p_hist.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    svc = DeployerService()

    if args.cmd == "status":
        _print(svc.status())
    elif args.cmd == "check":
        _print(svc.check())
    elif args.cmd == "history":
        _print(svc.history(limit=args.limit))


if __name__ == "__main__":
    main()
