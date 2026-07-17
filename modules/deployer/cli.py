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

    p_pend = sub.add_parser("pending", help="list deploy requests awaiting approval")
    p_pend.add_argument("--status", default=None,
                        choices=["pending_approval", "approved", "deployed",
                                 "failed", "rejected"])

    p_appr = sub.add_parser("approve", help="approve a pending deploy and execute it")
    p_appr.add_argument("--request-id", required=True)
    p_appr.add_argument("--actor", default="cli")

    p_rej = sub.add_parser("reject", help="reject a pending deploy")
    p_rej.add_argument("--request-id", required=True)
    p_rej.add_argument("--actor", default="cli")

    args = parser.parse_args()
    svc = DeployerService()

    if args.cmd == "status":
        _print(svc.status())
    elif args.cmd == "check":
        _print(svc.check())
    elif args.cmd == "history":
        _print(svc.history(limit=args.limit))
    elif args.cmd == "pending":
        _print(svc.list_pending_deploys(status=args.status))
    elif args.cmd == "approve":
        _print(svc.approve_deploy(args.request_id, actor=args.actor, via="cli"))
    elif args.cmd == "reject":
        _print(svc.reject_deploy(args.request_id, actor=args.actor))


if __name__ == "__main__":
    main()
