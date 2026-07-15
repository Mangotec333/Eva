#!/usr/bin/env python3
"""
EVA Agent Builder — CLI for the meta-agent that builds agents.

Examples:
  python cli.py catalog [--write]                 # inventory agents (+refresh catalog md)
  python cli.py scaffold --name "Invoice Agent" [--purpose "..."] [--port 8790] [--launchd] [--notify]
  python cli.py capture  --name "Explainer video build" \\
                         --step "Draft script" --step "Record VO" --step "Edit in media-editor" \\
                         [--trigger manual] [--summary "..."] [--input "topic"] [--module media-editor] [--notify]
  python cli.py scaffolds                          # list scaffolds this builder created
  python cli.py sops                               # list captured SOPs
"""

from __future__ import annotations

import argparse
import json

import agent_builder as ab
import store


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="EVA Agent Builder — inventory, scaffold, capture")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_cat = sub.add_parser("catalog", help="inventory every existing agent/module")
    p_cat.add_argument("--write", action="store_true",
                       help="refresh the auto-inventory block in EVA_AGENT_CATALOG.md")

    p_sc = sub.add_parser("scaffold", help="scaffold a brand-new agent/module")
    p_sc.add_argument("--name", required=True)
    p_sc.add_argument("--purpose", default="")
    p_sc.add_argument("--port", type=int, default=None)
    p_sc.add_argument("--launchd", action="store_true")
    p_sc.add_argument("--notify", action="store_true", help="post a Slack notification")

    p_cap = sub.add_parser("capture", help="capture a one-off workflow as a repeatable SOP")
    p_cap.add_argument("--name", required=True)
    p_cap.add_argument("--step", action="append", default=[], dest="steps",
                       help="repeatable; one --step per workflow step")
    p_cap.add_argument("--trigger", default="manual")
    p_cap.add_argument("--summary", default="")
    p_cap.add_argument("--input", action="append", default=[], dest="inputs",
                       help="repeatable; one --input per required input")
    p_cap.add_argument("--module", default="", help="attach SOP to a module dir")
    p_cap.add_argument("--notify", action="store_true", help="post a Slack notification")

    sub.add_parser("scaffolds", help="list scaffolds created by the builder")
    sub.add_parser("sops", help="list captured SOPs")

    args = p.parse_args()

    if args.cmd == "catalog":
        _print(ab.catalog(write=args.write))
    elif args.cmd == "scaffold":
        _print(ab.scaffold(args.name, purpose=args.purpose, port=args.port,
                           with_launchd=args.launchd, notify=args.notify))
    elif args.cmd == "capture":
        _print(ab.capture(args.name, steps=args.steps, trigger=args.trigger,
                          summary=args.summary, inputs=args.inputs,
                          module=args.module, notify=args.notify))
    elif args.cmd == "scaffolds":
        _print(store.list_scaffolds())
    elif args.cmd == "sops":
        _print(store.list_sops())


if __name__ == "__main__":
    main()
