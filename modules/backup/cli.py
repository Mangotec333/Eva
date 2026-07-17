"""
EVA Backup — CLI (framework-free; no fastapi import).

Usage:
  python cli.py tick                 Run one backup cycle
  python cli.py status               Show config + last run + Drive archives
  python cli.py ledger [--event ..]  Show the append-only audit trail

Offline by default (StubDriveClient). Set EVA_BACKUP_DRIVE=real +
EVA_BACKUP_DRIVE_FOLDER_ID to hit real Google Drive.
"""

from __future__ import annotations

import argparse
import json

from service import BackupService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eva-backup", description="EVA Backup CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tick", help="Run one backup cycle")
    sub.add_parser("status", help="Show config + last run + Drive archives")

    p_ledger = sub.add_parser("ledger", help="Show the append-only audit trail")
    p_ledger.add_argument("--event", dest="event_type", default=None,
                          help="Filter by event_type (backup_ok|backup_error|retention_delete)")
    p_ledger.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)
    svc = BackupService()

    if args.cmd == "tick":
        out = svc.tick(actor="cli")
    elif args.cmd == "status":
        out = svc.status()
    elif args.cmd == "ledger":
        out = svc.store.query_ledger(event_type=args.event_type, limit=args.limit)
    else:  # pragma: no cover - argparse enforces
        parser.print_help()
        return 2

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
