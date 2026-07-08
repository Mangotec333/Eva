"""
EVA Outreach — terminal-first CLI.

Lets the founder drive the approval-gated queue, opt-outs, and verifications
from the terminal (voice/terminal-first workflow). Mirrors spec section 6:

  outreach contacts add|list
  outreach campaign create --file email.md --to-list contacts.csv
  outreach pending
  outreach approve <rid>            outreach deny <rid> <reason>
  outreach send <rid>
  outreach optout <email> [--reason]
  outreach verify create <contact_id> [--method]
  outreach verify advance <case_id> --status verified --verifier <name>
  outreach ledger [--export csv]

Run:  python cli.py <command> ...   (or wire under `eva outreach ...`)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Optional

from service import ComplianceError, NotFoundError, OutreachService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Campaign file parsing
# ---------------------------------------------------------------------------

def _parse_email_file(path: str) -> dict:
    """Parse a simple email markdown file.

    Recognises leading ``Subject:``, ``From:``, ``FromEmail:``, ``FromAddress:``
    header lines; everything after the first blank line (or after the headers)
    is the body. A ``---`` line separates the body from a disclosures footer.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    subject = ""
    sender_name = sender_email = sender_address = ""
    lines = raw.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if low.startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
        elif low.startswith("from:"):
            sender_name = line.split(":", 1)[1].strip()
        elif low.startswith("fromemail:"):
            sender_email = line.split(":", 1)[1].strip()
        elif low.startswith("fromaddress:"):
            sender_address = line.split(":", 1)[1].strip()
        elif line.strip() == "":
            body_start = i + 1
            break
        else:
            body_start = i
            break

    remainder = "\n".join(lines[body_start:]).strip()
    disclosures = ""
    if "\n---\n" in remainder:
        body, disclosures = remainder.split("\n---\n", 1)
        body = body.strip()
        disclosures = disclosures.strip()
    else:
        body = remainder

    return {
        "subject": subject,
        "body": body,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_address": sender_address,
        "disclosures_text": disclosures,
    }


def _parse_contacts_csv(path: str) -> list[dict]:
    """Parse a CSV of contacts. Requires an ``email`` column; optional
    ``name``, ``relationship_type``, ``source`` columns."""
    contacts = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            email = (row.get("email") or "").strip()
            if not email:
                continue
            contacts.append(
                {
                    "email": email,
                    "name": (row.get("name") or "").strip(),
                    "relationship_type": (row.get("relationship_type") or "cold").strip(),
                    "source": (row.get("source") or "import").strip(),
                }
            )
    return contacts


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_contacts(svc: OutreachService, args) -> None:
    if args.action == "add":
        contact = svc.add_contact(
            {
                "email": args.email,
                "name": args.name or "",
                "relationship_type": args.relationship_type,
                "source": args.source,
            }
        )
        _print(contact)
    elif args.action == "list":
        _print(svc.list_contacts(relationship_type=args.relationship_type))


def cmd_campaign(svc: OutreachService, args) -> None:
    if args.action == "create":
        fields = _parse_email_file(args.file)
        fields["name"] = args.name or fields.get("subject") or "Untitled campaign"
        campaign = svc.create_campaign(fields)

        contact_ids = []
        if args.to_list:
            for row in _parse_contacts_csv(args.to_list):
                existing = svc.store.get_contact_by_email(row["email"])
                if existing:
                    contact_ids.append(existing["id"])
                else:
                    contact_ids.append(svc.add_contact(row)["id"])
        result = {"campaign": campaign, "recipients": None}
        if contact_ids:
            result["recipients"] = svc.add_recipients(campaign["id"], contact_ids, actor="cli")
        _print(result)


def cmd_pending(svc: OutreachService, args) -> None:
    _print(svc.list_pending())


def cmd_approve(svc: OutreachService, args) -> None:
    _print(svc.approve_recipient(args.rid, args.approved_by))


def cmd_deny(svc: OutreachService, args) -> None:
    _print(svc.deny_recipient(args.rid, actor=args.actor, reason=args.reason))


def cmd_send(svc: OutreachService, args) -> None:
    _print(svc.send_recipient(args.rid, actor=args.actor))


def cmd_optout(svc: OutreachService, args) -> None:
    _print(svc.add_suppression(args.email, reason=args.reason, source="cli", actor=args.actor))


def cmd_verify(svc: OutreachService, args) -> None:
    if args.action == "create":
        _print(svc.create_verification(args.contact_id, method=args.method, actor="cli"))
    elif args.action == "advance":
        _print(
            svc.advance_verification(
                args.case_id,
                status=args.status,
                verifier=args.verifier,
                documents_ref=args.documents_ref,
                notes=args.notes,
                actor="cli",
            )
        )


def cmd_sale(svc: OutreachService, args) -> None:
    _print(svc.record_sale(args.contact_id, amount=args.amount, actor="cli"))


def cmd_ledger(svc: OutreachService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="outreach", description="EVA Outreach CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_contacts = sub.add_parser("contacts", help="Manage contacts")
    p_contacts.add_argument("action", choices=["add", "list"])
    p_contacts.add_argument("--email")
    p_contacts.add_argument("--name")
    p_contacts.add_argument("--relationship-type", dest="relationship_type", default="cold")
    p_contacts.add_argument("--source", default="cli")
    p_contacts.set_defaults(func=cmd_contacts)

    p_campaign = sub.add_parser("campaign", help="Manage campaigns")
    p_campaign.add_argument("action", choices=["create"])
    p_campaign.add_argument("--file", required=True, help="email.md file")
    p_campaign.add_argument("--to-list", dest="to_list", help="contacts.csv file")
    p_campaign.add_argument("--name")
    p_campaign.set_defaults(func=cmd_campaign)

    p_pending = sub.add_parser("pending", help="List pending_approval recipients")
    p_pending.set_defaults(func=cmd_pending)

    p_approve = sub.add_parser("approve", help="Approve a recipient")
    p_approve.add_argument("rid")
    p_approve.add_argument("--approved-by", dest="approved_by", default="founder")
    p_approve.set_defaults(func=cmd_approve)

    p_deny = sub.add_parser("deny", help="Deny a recipient")
    p_deny.add_argument("rid")
    p_deny.add_argument("reason", nargs="?", default="")
    p_deny.add_argument("--actor", default="founder")
    p_deny.set_defaults(func=cmd_deny)

    p_send = sub.add_parser("send", help="Send an approved recipient")
    p_send.add_argument("rid")
    p_send.add_argument("--actor", default="founder")
    p_send.set_defaults(func=cmd_send)

    p_optout = sub.add_parser("optout", help="Add an email to the suppression list")
    p_optout.add_argument("email")
    p_optout.add_argument("--reason", default="opt_out")
    p_optout.add_argument("--actor", default="founder")
    p_optout.set_defaults(func=cmd_optout)

    p_verify = sub.add_parser("verify", help="Investor verification workflow")
    verify_sub = p_verify.add_subparsers(dest="action", required=True)
    v_create = verify_sub.add_parser("create")
    v_create.add_argument("contact_id")
    v_create.add_argument("--method", default="")
    v_advance = verify_sub.add_parser("advance")
    v_advance.add_argument("case_id")
    v_advance.add_argument("--status", required=True)
    v_advance.add_argument("--verifier", default="")
    v_advance.add_argument("--documents-ref", dest="documents_ref", default="")
    v_advance.add_argument("--notes", default="")
    p_verify.set_defaults(func=cmd_verify)

    p_sale = sub.add_parser("sale", help="Record a sale (506(c) gated)")
    p_sale.add_argument("contact_id")
    p_sale.add_argument("--amount", type=float, default=0.0)
    p_sale.set_defaults(func=cmd_sale)

    p_ledger = sub.add_parser("ledger", help="Query/export the compliance ledger")
    p_ledger.add_argument("--export", choices=["csv", "json"])
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = OutreachService()
    try:
        args.func(svc, args)
        return 0
    except (ComplianceError, NotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
