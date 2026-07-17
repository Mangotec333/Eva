"""
EVA Health Monitor — terminal-first CLI.

Matches sibling module style:

  python cli.py tick                     probe all modules, record, alert (cron-safe)
  python cli.py status                   latest status per monitored module
  python cli.py modules                  the monitored-module config list
  python cli.py checks [--module m] [--limit n]
  python cli.py alerts [--status open|resolved]
  python cli.py ledger [--event-type ...]

Defaults to the real urllib probe; set EVA_HEALTH_CLIENT=stub for an offline
dry-run (no sockets). Wire under `eva health-monitor ...` if desired.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import HealthMonitorService, NotFoundError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_tick(svc: HealthMonitorService, args) -> None:
    result = svc.tick(actor="cli")
    _print({k: result[k] for k in
            ("monitored", "up", "down", "new_alerts", "resolved_alerts")})


def cmd_status(svc: HealthMonitorService, args) -> None:
    _print(svc.status())


def cmd_modules(svc: HealthMonitorService, args) -> None:
    _print(svc.list_targets())


def cmd_checks(svc: HealthMonitorService, args) -> None:
    _print(svc.recent_checks(module=args.module, limit=args.limit))


def cmd_alerts(svc: HealthMonitorService, args) -> None:
    _print(svc.list_alerts(status=args.status))


def cmd_ledger(svc: HealthMonitorService, args) -> None:
    _print(svc.query_ledger(event_type=args.event_type))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="health-monitor", description="EVA Health Monitor CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tick = sub.add_parser("tick", help="Probe all modules, record, alert (cron-safe)")
    p_tick.set_defaults(func=cmd_tick)

    p_status = sub.add_parser("status", help="Latest status per monitored module")
    p_status.set_defaults(func=cmd_status)

    p_modules = sub.add_parser("modules", help="Show the monitored-module config list")
    p_modules.set_defaults(func=cmd_modules)

    p_checks = sub.add_parser("checks", help="Recent raw health-check rows")
    p_checks.add_argument("--module")
    p_checks.add_argument("--limit", type=int, default=100)
    p_checks.set_defaults(func=cmd_checks)

    p_alerts = sub.add_parser("alerts", help="List alerts")
    p_alerts.add_argument("--status", choices=["open", "resolved"])
    p_alerts.set_defaults(func=cmd_alerts)

    p_ledger = sub.add_parser("ledger", help="Query the append-only ledger")
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = HealthMonitorService()
    try:
        args.func(svc, args)
        return 0
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
