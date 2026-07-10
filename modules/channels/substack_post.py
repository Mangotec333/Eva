"""
EVA Channels — Substack chokepoint (honest MVP: no reliable public posting API).

Contract (spec section 7)
--------------------------
stdin  : {"id", "title", "body", "publication_url", "session_env"}
stdout : {"ok": false, "provider": "substack", "post_url": "",
          "needs_manual_publish": true, "error": "..."}

Substack has no reliable public posting API, so v1 NEVER fakes ``ok=true``.
Instead it ALWAYS exports a ready-to-publish markdown draft to
``data/channels/substack/<id>.md`` and returns ``needs_manual_publish=true`` with
a clear error telling the operator to publish it manually in the Substack
editor.

v2 (documented in README): browser automation with a captured
``SUBSTACK_SESSION_COOKIE`` driving the Substack editor to create/publish a
draft. Deliberately out of scope for v1.
"""

from __future__ import annotations

import json
import os
import re
import sys

DRAFT_DIR = os.environ.get(
    "EVA_CHANNELS_SUBSTACK_DIR",
    os.path.join(os.path.dirname(__file__), "data", "channels", "substack"),
)


def _safe_id(value: str) -> str:
    """A filesystem-safe file stem derived from the item id/title."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value or "draft")
    return cleaned[:120] or "draft"


def _export_draft(req: dict) -> str:
    """Write the item as a markdown draft and return the file path."""
    os.makedirs(DRAFT_DIR, exist_ok=True)
    stem = _safe_id(str(req.get("id") or req.get("title") or "draft"))
    path = os.path.join(DRAFT_DIR, f"{stem}.md")
    title = req.get("title", "")
    body = req.get("body", "")
    pub = req.get("publication_url", "")
    lines = [f"# {title}", ""]
    if pub:
        lines.append(f"<!-- publication: {pub} -->")
        lines.append("")
    lines.append(body)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return path


def _post_via_substack(req: dict) -> dict:
    """Always export a markdown draft; never fake success (spec section 7)."""
    path = _export_draft(req)
    return {
        "ok": False,
        "provider": "substack",
        "post_url": "",
        "needs_manual_publish": True,
        "error": (
            "Substack has no public posting API — draft exported to "
            f"{path}, publish manually in editor"
        ),
        "draft_path": path,
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        req = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "ok": False, "provider": "substack", "post_url": "",
            "needs_manual_publish": True,
            "error": f"invalid request JSON: {exc}",
        }))
        return 0

    try:
        result = _post_via_substack(req)
    except Exception as exc:  # noqa: BLE001 — chokepoint must not crash caller
        result = {
            "ok": False, "provider": "substack", "post_url": "",
            "needs_manual_publish": True,
            "error": f"substack_post.py error: {exc}",
        }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
