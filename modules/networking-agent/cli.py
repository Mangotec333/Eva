"""
EVA Networking-Agent — terminal-first CLI (mirrors modules/outreach/cli.py).

Drive both layers and the approval loop from the terminal:

  python cli.py seed
  python cli.py plan --venture eva_growth_agency
  python cli.py directives --venture storeys

  python cli.py groups discover --venture eva_growth_agency --seed seed.json
  python cli.py groups list [--venture ..] [--platform ..] [--status ..]
  python cli.py groups score <id>

  python cli.py draft <group_id> --content "…" [--action comment] [--entity-type group]
  python cli.py groups approve <draft_id>
  python cli.py groups send <draft_id>
  python cli.py auto <action> <group_id>          # whitelisted actions only
  python cli.py log-outcome <group_id> --outcome reply --signal reply_received

  python cli.py contacts list
  python cli.py kaizen reweight
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from service import NetworkingAgentService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_seed(svc: NetworkingAgentService, args) -> None:
    _print(svc.seed())


def cmd_plan(svc: NetworkingAgentService, args) -> None:
    _print(svc.plan(args.venture))


def cmd_directives(svc: NetworkingAgentService, args) -> None:
    _print(svc.get_directive(args.venture))


def cmd_groups(svc: NetworkingAgentService, args) -> None:
    if args.action == "discover":
        seed = args.seed
        _print(svc.discover(args.venture, seed, provider=args.provider))
    elif args.action == "list":
        rows = svc.list_groups(venture=args.venture, platform=args.platform,
                               status=args.status)
        _print({"groups": rows, "count": len(rows)})
    elif args.action == "score":
        _print(svc.score(args.id))
    elif args.action == "approve":
        _print(svc.approve(args.id, approved_by=args.approved_by))
    elif args.action == "send":
        _print(svc.send(args.id, actor=args.actor))


def cmd_draft(svc: NetworkingAgentService, args) -> None:
    _print(svc.draft(args.entity_type, args.entity_id, args.content, action=args.action))


def cmd_auto(svc: NetworkingAgentService, args) -> None:
    _print(svc.auto_action(args.action, args.entity_id,
                           entity_type=args.entity_type, actor="cli"))


def cmd_log_outcome(svc: NetworkingAgentService, args) -> None:
    _print(svc.log_outcome(args.entity_type, args.entity_id, args.outcome,
                           signal=args.signal, actor="cli"))


def cmd_contacts(svc: NetworkingAgentService, args) -> None:
    if args.action == "list":
        rows = svc.list_contacts(venture=args.venture, stage=args.stage)
        _print({"contacts": rows, "count": len(rows)})


def cmd_kaizen(svc: NetworkingAgentService, args) -> None:
    if args.action == "reweight":
        _print(svc.kaizen_reweight())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="networking", description="EVA Networking-Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Initialise store + snapshot directives")
    p_seed.set_defaults(func=cmd_seed)

    p_plan = sub.add_parser("plan", help="Directive-aware plan for a venture")
    p_plan.add_argument("--venture", required=True)
    p_plan.set_defaults(func=cmd_plan)

    p_dir = sub.add_parser("directives", help="Show resolved directive for a venture")
    p_dir.add_argument("--venture", required=True)
    p_dir.set_defaults(func=cmd_directives)

    p_groups = sub.add_parser("groups", help="Group discovery / scoring / approval")
    g_sub = p_groups.add_subparsers(dest="action", required=True)
    g_disc = g_sub.add_parser("discover")
    g_disc.add_argument("--venture", required=True)
    g_disc.add_argument("--seed", required=True, help="JSON/CSV/markdown seed file")
    g_disc.add_argument("--provider", default="manual_seed")
    g_list = g_sub.add_parser("list")
    g_list.add_argument("--venture")
    g_list.add_argument("--platform")
    g_list.add_argument("--status")
    g_score = g_sub.add_parser("score")
    g_score.add_argument("id")
    g_appr = g_sub.add_parser("approve")
    g_appr.add_argument("id", help="draft id")
    g_appr.add_argument("--approved-by", dest="approved_by", default="founder")
    g_send = g_sub.add_parser("send")
    g_send.add_argument("id", help="draft id")
    g_send.add_argument("--actor", default="founder")
    p_groups.set_defaults(func=cmd_groups)

    p_draft = sub.add_parser("draft", help="Draft outbound content (approval-gated)")
    p_draft.add_argument("entity_id")
    p_draft.add_argument("--content", required=True)
    p_draft.add_argument("--action", default="post")
    p_draft.add_argument("--entity-type", dest="entity_type", default="group")
    p_draft.set_defaults(func=cmd_draft)

    p_auto = sub.add_parser("auto", help="Run a whitelisted autonomous action")
    p_auto.add_argument("action")
    p_auto.add_argument("entity_id")
    p_auto.add_argument("--entity-type", dest="entity_type", default="group")
    p_auto.set_defaults(func=cmd_auto)

    p_log = sub.add_parser("log-outcome", help="Log a KAIZEN outcome signal")
    p_log.add_argument("entity_id")
    p_log.add_argument("--outcome", required=True)
    p_log.add_argument("--signal", default="")
    p_log.add_argument("--entity-type", dest="entity_type", default="group")
    p_log.set_defaults(func=cmd_log_outcome)

    p_contacts = sub.add_parser("contacts", help="Layer A contacts")
    c_sub = p_contacts.add_subparsers(dest="action", required=True)
    c_list = c_sub.add_parser("list")
    c_list.add_argument("--venture")
    c_list.add_argument("--stage")
    p_contacts.set_defaults(func=cmd_contacts)

    p_kaizen = sub.add_parser("kaizen", help="KAIZEN outcome-weighting loop")
    k_sub = p_kaizen.add_subparsers(dest="action", required=True)
    k_sub.add_parser("reweight")
    p_kaizen.set_defaults(func=cmd_kaizen)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = NetworkingAgentService()
    args.func(svc, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
