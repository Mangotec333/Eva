"""
EVA IP-Scout — seed CLI.

Adds an invention-idea seed to ~/.eva/ip_ideas.json (or EVA_IP_IDEAS_FILE) so it
gets picked up by the next triage scan.

Usage:
  python modules/ip-scout/seed.py --title "..." [--desc "..."] [--category "..."]
  python modules/ip-scout/seed.py --scan   # seed nothing, just run a scan
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service import IPScoutService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed an IP-Scout invention idea")
    parser.add_argument("--title", type=str, default=None, help="Idea title")
    parser.add_argument("--desc", type=str, default="", help="Idea description")
    parser.add_argument("--category", type=str, default="uncategorized")
    parser.add_argument("--id", type=str, default=None, help="Explicit idea id")
    parser.add_argument("--scan", action="store_true", help="Run a triage scan after seeding")
    args = parser.parse_args()

    svc = IPScoutService()
    out: dict = {}
    if args.title:
        idea = svc.seed_idea(title=args.title, description=args.desc,
                             category=args.category, idea_id=args.id)
        out["seeded"] = idea
    if args.scan or not args.title:
        res = svc.scan()
        res.pop("disclosures", None)
        out["scan"] = res
    print(json.dumps(out, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
