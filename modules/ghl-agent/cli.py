"""
EVA GHL Agent — terminal-first CLI.

Drive the GoHighLevel integration from the terminal:

  ghl build-funnel                 run the idempotent one-time build (Part 1)
  ghl funnel-status                show which build pieces exist
  ghl capture-lead <email> [...]   capture a lead into the acquisition funnel
  ghl events [--email ...]         list local lead-lifecycle ledger events
  ghl webhook '<json>'             feed a GHL event through the webhook handler
  ghl campaign                     print the 7-touch sequence (voice check)

Run:  python cli.py <command> ...
Offline by default in the sandbox; set GHL_ACCESS_TOKEN for live GHL, or
EVA_GHL_OFFLINE=1 to force stubs.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

import campaign
from service import CaptureError, GHLAgentService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_build_funnel(svc: GHLAgentService, args) -> None:
    _print(svc.build_funnel())


def cmd_funnel_status(svc: GHLAgentService, args) -> None:
    _print(svc.funnel_status())


def cmd_capture_lead(svc: GHLAgentService, args) -> None:
    _print(svc.capture_lead(email=args.email, name=args.name or "",
                            phone=args.phone or "",
                            source=args.source or "eva-acquisition"))


def cmd_events(svc: GHLAgentService, args) -> None:
    _print(svc.lead_events(email=args.email, event_type=args.type, limit=args.limit))


def cmd_webhook(svc: GHLAgentService, args) -> None:
    try:
        event = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    _print(svc.handle_webhook(event))


def cmd_campaign(svc: GHLAgentService, args) -> None:
    report = campaign.validate_touches()
    if args.raw:
        _print({"validation": report, "touches": campaign.render_touches()})
        return
    print(f"Campaign: {campaign.CAMPAIGN_NAME}")
    print(f"Trigger tag: {campaign.TRIGGER_TAG}")
    print(f"Voice validation: {'OK' if report['ok'] else report['problems']}\n")
    for t in campaign.render_touches():
        head = f"[{t['order']}] Day {t['day']} · {t['channel'].upper()} · {t['name']}"
        print(head)
        if t.get("subject"):
            print(f"    Subject: {t['subject']}")
        for line in t["body"].splitlines():
            print(f"    {line}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ghl", description="EVA GHL Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build-funnel", help="Run the idempotent one-time build")
    p_build.set_defaults(func=cmd_build_funnel)

    p_status = sub.add_parser("funnel-status", help="Show which build pieces exist")
    p_status.set_defaults(func=cmd_funnel_status)

    p_cap = sub.add_parser("capture-lead", help="Capture a lead into the funnel")
    p_cap.add_argument("email")
    p_cap.add_argument("--name", default="")
    p_cap.add_argument("--phone", default="")
    p_cap.add_argument("--source", default="eva-acquisition")
    p_cap.set_defaults(func=cmd_capture_lead)

    p_ev = sub.add_parser("events", help="List local lead-lifecycle ledger events")
    p_ev.add_argument("--email", default=None)
    p_ev.add_argument("--type", default=None)
    p_ev.add_argument("--limit", type=int, default=50)
    p_ev.set_defaults(func=cmd_events)

    p_wh = sub.add_parser("webhook", help="Feed a GHL event JSON through the handler")
    p_wh.add_argument("json", help="the event as a JSON string")
    p_wh.set_defaults(func=cmd_webhook)

    p_camp = sub.add_parser("campaign", help="Print/validate the 7-touch sequence")
    p_camp.add_argument("--raw", action="store_true")
    p_camp.set_defaults(func=cmd_campaign)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = GHLAgentService()
    try:
        args.func(svc, args)
        return 0
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
