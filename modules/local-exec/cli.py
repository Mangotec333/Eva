#!/usr/bin/env python3
"""
EVA Local-Exec — CLI mirror of the service routes.

Examples:
  python cli.py exec git status                 # allowlisted → runs now
  python cli.py exec -- git log --oneline -5    # use -- to pass flags through
  python cli.py exec --cwd ~/eva-landing vercel --prod
  python cli.py status                          # allowlist summary + run counts
  python cli.py history --limit 20              # recent audited runs
  python cli.py approve <run_id>                # approve a pending run
  python cli.py approve <run_id> --deny         # deny a pending run

Offline-safe: set EVA_LOCAL_EXEC_OFFLINE=1 to never spawn a subprocess (a mocked
no-op is returned). That is the default posture in the sandbox.
"""

from __future__ import annotations

import argparse
import json

from service import LocalExecService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Local-Exec CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exec = sub.add_parser("exec", help="run a command (allowlisted → now; else gated)")
    p_exec.add_argument("--cwd", default=None, help="working directory")
    p_exec.add_argument("--timeout", type=int, default=None, help="exec timeout (s)")
    p_exec.add_argument("--triggered-by", default="cli", help="who triggered this run")
    p_exec.add_argument("argv", nargs=argparse.REMAINDER,
                        help="the command + args (prefix with -- to pass flags)")

    sub.add_parser("status", help="allowlist summary + run counts")

    p_hist = sub.add_parser("history", help="recent audited runs (newest first)")
    p_hist.add_argument("--limit", type=int, default=20)

    p_appr = sub.add_parser("approve", help="approve/deny a pending run")
    p_appr.add_argument("run_id")
    p_appr.add_argument("--deny", action="store_true", help="deny instead of approve")

    args = parser.parse_args()
    svc = LocalExecService()

    if args.cmd == "exec":
        argv = list(args.argv)
        if argv and argv[0] == "--":
            argv = argv[1:]
        if not argv:
            parser.error("exec needs a command")
        _print(svc.exec_command(argv[0], args=argv[1:], cwd=args.cwd,
                                triggered_by=args.triggered_by, timeout=args.timeout))
    elif args.cmd == "status":
        _print(svc.status())
    elif args.cmd == "history":
        _print(svc.history(limit=args.limit))
    elif args.cmd == "approve":
        _print(svc.approve(args.run_id, approved=not args.deny, actor="cli"))


if __name__ == "__main__":
    main()
