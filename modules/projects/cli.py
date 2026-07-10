"""
EVA Projects — terminal-first CLI.

Lets the founder drive the roadmap tree from the terminal (voice/terminal-first
workflow). Mirrors spec section 6:

  projects seed
  projects import --file roadmap.json
  projects export [--file roadmap.json]
  projects add --title "..." --parent <id> --tier t1 --status pending
  projects list
  projects update <id> --status done
  projects move <id> --parent <id>
  projects delete <id>
  projects ledger [--export csv]

Run:  python cli.py <command> ...   (or wire under `eva projects ...`)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from service import NotFoundError, ProjectError, ProjectsService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_seed(svc: ProjectsService, args) -> None:
    result = svc.seed(actor="cli")
    _print({"created": result["created"], "skipped": result["skipped"]})


def cmd_import(svc: ProjectsService, args) -> None:
    with open(args.file, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    nodes = doc["nodes"] if isinstance(doc, dict) and "nodes" in doc else doc
    _print(svc.import_tree(nodes, actor="cli"))


def cmd_export(svc: ProjectsService, args) -> None:
    tree = svc.export_tree()
    payload = {"nodes": tree}
    if args.file:
        with open(args.file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        _print({"exported": len(tree), "file": args.file})
    else:
        _print(payload)


def cmd_add(svc: ProjectsService, args) -> None:
    _print(
        svc.create_node(
            {
                "title": args.title,
                "parent_id": args.parent,
                "tier": args.tier,
                "status": args.status,
                "meta": args.meta or "",
                "link": args.link or "",
                "actor": "cli",
            }
        )
    )


def cmd_list(svc: ProjectsService, args) -> None:
    if args.tree:
        _print(svc.get_tree())
    else:
        _print(svc.list_nodes())


def cmd_update(svc: ProjectsService, args) -> None:
    fields = {
        "title": args.title,
        "tier": args.tier,
        "status": args.status,
        "meta": args.meta,
        "link": args.link,
    }
    _print(svc.update_node(args.id, fields, actor="cli"))


def cmd_move(svc: ProjectsService, args) -> None:
    _print(svc.move_node(args.id, args.parent, actor="cli"))


def cmd_delete(svc: ProjectsService, args) -> None:
    _print(svc.delete_node(args.id, actor="cli"))


def cmd_ledger(svc: ProjectsService, args) -> None:
    if args.export:
        print(svc.export_ledger(args.export))
    else:
        _print(svc.query_ledger(event_type=args.event_type))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="projects", description="EVA Projects CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Load the roadmap tree (idempotent on title)")
    p_seed.set_defaults(func=cmd_seed)

    p_import = sub.add_parser("import", help="Replace the tree from a JSON file")
    p_import.add_argument("--file", required=True, help="Path to roadmap JSON")
    p_import.set_defaults(func=cmd_import)

    p_export = sub.add_parser("export", help="Export the tree as JSON")
    p_export.add_argument("--file", help="Write to file (default: stdout)")
    p_export.set_defaults(func=cmd_export)

    p_add = sub.add_parser("add", help="Add a node")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--parent", help="Parent node id (omit for a root)")
    p_add.add_argument("--tier", choices=["t1", "t2", "t3", "none"], default="none")
    p_add.add_argument("--status", choices=["done", "inprog", "pending", ""], default="")
    p_add.add_argument("--meta")
    p_add.add_argument("--link")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List nodes")
    p_list.add_argument("--tree", action="store_true", help="Nested tree instead of flat")
    p_list.set_defaults(func=cmd_list)

    p_update = sub.add_parser("update", help="Update a node")
    p_update.add_argument("id")
    p_update.add_argument("--title")
    p_update.add_argument("--tier", choices=["t1", "t2", "t3", "none"])
    p_update.add_argument("--status", choices=["done", "inprog", "pending", ""])
    p_update.add_argument("--meta")
    p_update.add_argument("--link")
    p_update.set_defaults(func=cmd_update)

    p_move = sub.add_parser("move", help="Reparent a node")
    p_move.add_argument("id")
    p_move.add_argument("--parent", help="New parent id (omit for a root)")
    p_move.set_defaults(func=cmd_move)

    p_delete = sub.add_parser("delete", help="Delete a node (cascades to subtree)")
    p_delete.add_argument("id")
    p_delete.set_defaults(func=cmd_delete)

    p_ledger = sub.add_parser("ledger", help="Query/export the change ledger")
    p_ledger.add_argument("--export", choices=["csv", "json"])
    p_ledger.add_argument("--event-type", dest="event_type")
    p_ledger.set_defaults(func=cmd_ledger)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = ProjectsService()
    try:
        args.func(svc, args)
        return 0
    except (ProjectError, NotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
