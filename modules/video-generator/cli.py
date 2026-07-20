"""
EVA Video Generator — terminal-first CLI.

Drive the script-to-video pipeline from the terminal (matches sibling module
style, e.g. `eva video-generator <cmd>`):

  video-generator seed
  video-generator list [--status draft|storyboard_ready|approved|rendering|rendered|failed]
  video-generator create "<title>" "<script text>"
  video-generator storyboard <id>
  video-generator approve <id>
  video-generator render <id>
  video-generator status <id>
  video-generator ledger [<id>]

Run:  python cli.py <command> ...   (or wire under `eva video-generator ...`)
"""

from __future__ import annotations

import argparse
import json
import sys

from service import VideoGenError, VideoGeneratorService


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_seed(svc, args) -> None:
    _print(svc.seed(actor="cli"))


def cmd_list(svc, args) -> None:
    _print(svc.list_videos(status=args.status))


def cmd_create(svc, args) -> None:
    _print(svc.create_video(title=args.title, script_text=args.script_text, actor="cli"))


def cmd_storyboard(svc, args) -> None:
    _print(svc.storyboard(args.id, actor="cli"))


def cmd_approve(svc, args) -> None:
    _print(svc.approve(args.id, actor="cli"))


def cmd_render(svc, args) -> None:
    _print(svc.render(args.id, actor="cli"))


def cmd_status(svc, args) -> None:
    _print(svc.get_video(args.id))


def cmd_ledger(svc, args) -> None:
    _print(svc.ledger(args.id))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="video-generator",
                                description="EVA Video Generator CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="idempotent demo seed")

    p_list = sub.add_parser("list", help="list videos")
    p_list.add_argument("--status", default=None)

    p_create = sub.add_parser("create", help="create a video from a script")
    p_create.add_argument("title")
    p_create.add_argument("script_text")

    for name, help_ in (("storyboard", "segment + render slides"),
                        ("approve", "approve for render (compute gate)"),
                        ("render", "render the MP4"),
                        ("status", "show one video")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("id")

    p_ledger = sub.add_parser("ledger", help="show event ledger")
    p_ledger.add_argument("id", nargs="?", default=None)
    return p


_HANDLERS = {
    "seed": cmd_seed, "list": cmd_list, "create": cmd_create,
    "storyboard": cmd_storyboard, "approve": cmd_approve, "render": cmd_render,
    "status": cmd_status, "ledger": cmd_ledger,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    svc = VideoGeneratorService()
    try:
        _HANDLERS[args.command](svc, args)
    except VideoGenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
