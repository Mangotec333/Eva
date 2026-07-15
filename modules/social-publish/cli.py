#!/usr/bin/env python3
"""
EVA Social-Publish — CLI for the approve-then-publish gate.

Examples:
  python cli.py creds                       # show LinkedIn + X credential status
  python cli.py submit --text "..." [--image path] [--platforms linkedin,x]
  python cli.py list [--status pending_approval]
  python cli.py check                       # poll Slack for approvals, publish approved
  python cli.py approve <draft_id>          # explicit approve + publish (local)
  python cli.py reject <draft_id>
  python cli.py status <draft_id>
"""

from __future__ import annotations

import argparse
import json

import credentials
import gate
import store


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA social approve-then-publish gate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("creds", help="show LinkedIn + X credential status")

    p_submit = sub.add_parser("submit", help="submit a draft for Slack approval")
    p_submit.add_argument("--text", required=True)
    p_submit.add_argument("--image", default="")
    p_submit.add_argument("--platforms", default="linkedin,x")

    p_list = sub.add_parser("list", help="list drafts")
    p_list.add_argument("--status", default=None)

    sub.add_parser("check", help="poll Slack for approvals and publish approved drafts")

    p_ap = sub.add_parser("approve", help="approve + publish a draft")
    p_ap.add_argument("draft_id")

    p_rj = sub.add_parser("reject", help="reject a draft")
    p_rj.add_argument("draft_id")

    p_st = sub.add_parser("status", help="show one draft")
    p_st.add_argument("draft_id")

    args = parser.parse_args()

    if args.cmd == "creds":
        _print(credentials.detect())
    elif args.cmd == "submit":
        platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
        _print(gate.submit_for_approval(args.text, image_path=args.image, platforms=platforms))
    elif args.cmd == "list":
        _print(store.list_drafts(status=args.status))
    elif args.cmd == "check":
        _print(gate.check_slack_approvals())
    elif args.cmd == "approve":
        _print(gate.approve(args.draft_id, actor="cli", via="cli"))
    elif args.cmd == "reject":
        _print(gate.reject(args.draft_id, actor="cli"))
    elif args.cmd == "status":
        _print(store.get_draft(args.draft_id))


if __name__ == "__main__":
    main()
