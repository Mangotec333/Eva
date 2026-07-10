"""
EVA State Ledger — Kalpawriksha (Project Map) generator
=======================================================

Kalpawriksha stops being hand-edited HTML and becomes a *view* of the ledger.
:func:`build_tree` derives the project tree from the ledger's current (non-
superseded) events; :func:`render` writes ``project_map.json`` and, optionally,
a static ``index.html`` reusing the original map's CSS/visual shell — populated
from the JSON, not hand-maintained.

Badge/status mapping is the inverse of the importer's (see ``seed.py``):

    live        -> Production-Live   (b-live)
    in_progress -> In Progress       (b-prog)
    open        -> Open              (b-open)
    planned     -> Planned           (b-plan)
    blocked     -> Blocked           (b-block)
    dropped     -> Dropped           (b-plan, struck)
"""

from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime, timezone

import memory

HERE = os.path.dirname(__file__)
JSON_PATH = os.path.join(HERE, "project_map.json")
HTML_PATH = os.path.join(HERE, "project_map.html")
SHELL_HTML = os.path.join(HERE, "seed", "project_map_source.html")

# status -> (badge label, css class)
_BADGE = {
    memory.STATUS_LIVE:        ("Production-Live", "b-live"),
    memory.STATUS_IN_PROGRESS: ("In Progress", "b-prog"),
    memory.STATUS_OPEN:        ("Open", "b-open"),
    memory.STATUS_PLANNED:     ("Planned", "b-plan"),
    memory.STATUS_BLOCKED:     ("Blocked", "b-block"),
    memory.STATUS_DROPPED:     ("Dropped", "b-plan"),
    memory.STATUS_DONE:        ("Done", "b-live"),
    memory.STATUS_ACTIVE:      ("Active", "b-live"),
}


def _badge(status: str) -> tuple[str, str]:
    return _BADGE.get(status, (status.title() if status else "Open", "b-open"))


def build_tree(path: str = memory.DB_PATH) -> dict:
    """Derive the Kalpawriksha tree from the ledger's current standing events.

    Groups current (non-superseded) events by ``project`` then ``track``; each
    leaf is an entity's latest standing event, carrying its status badge.
    """
    # Current standing events (exclude those superseded by a later correction).
    current = [e for e in memory.list_events(path=path)
               if e["status"] != memory.STATUS_SUPERSEDED]

    projects: dict[str, dict] = {}
    for e in current:
        proj = e["project"] or "Unsorted"
        node = projects.setdefault(proj, {"project": proj, "tracks": {}})
        track = e["track"] or "general"
        tnode = node["tracks"].setdefault(track, {"track": track, "items": []})
        label, css = _badge(e["status"])
        tnode["items"].append({
            "entity_type": e["entity_type"],
            "entity_id": e["entity_id"],
            "summary": e["summary"],
            "event_type": e["event_type"],
            "status": e["status"],
            "badge": label,
            "badge_class": css,
            "evidence_urls": e["evidence_urls"],
            "updated_at": e["timestamp"],
        })

    # Roll project-level status up from the project_state_view.
    proj_status = {r["project"]: r["status"] for r in memory.project_state(path)}

    tree = []
    for proj in sorted(projects):
        node = projects[proj]
        status = proj_status.get(proj, "")
        blabel, bcss = _badge(status) if status else ("", "")
        tracks = [node["tracks"][t] for t in sorted(node["tracks"])]
        item_count = sum(len(t["items"]) for t in tracks)
        tree.append({
            "project": proj,
            "status": status,
            "badge": blabel,
            "badge_class": bcss,
            "item_count": item_count,
            "tracks": tracks,
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "eva-state ledger (derived)",
        "event_count": memory.event_count(path),
        "projects": tree,
    }


def render(path: str = memory.DB_PATH, *, write_json: bool = True,
           write_html: bool = False) -> dict:
    """Regenerate project_map.json (and optionally the static index.html)."""
    tree = build_tree(path)
    result: dict = {"tree": tree}
    if write_json:
        with open(JSON_PATH, "w", encoding="utf-8") as fh:
            json.dump(tree, fh, indent=2, default=str)
        result["json_path"] = JSON_PATH
    if write_html:
        html_doc = render_html(tree)
        with open(HTML_PATH, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
        result["html_path"] = HTML_PATH
    return result


def _tree_ul(tree: dict) -> str:
    """Render the tree JSON into the <ul class="tree"> body used by the shell."""
    parts = ['<ul class="tree" id="root">']
    for proj in tree["projects"]:
        badge = ""
        if proj["badge"]:
            badge = f' <span class="badge {proj["badge_class"]}">{_html.escape(proj["badge"])}</span>'
        parts.append('<li>')
        parts.append(
            f'<div class="node" onclick="tog(this)"><span class="caret open">▸</span>'
            f'<span class="lbl">{_html.escape(proj["project"])}</span>'
            f'<span class="count">· {proj["item_count"]}</span>{badge}</div>')
        parts.append('<ul>')
        for track in proj["tracks"]:
            for item in track["items"]:
                blabel = _html.escape(item["badge"])
                bcss = item["badge_class"]
                summary = _html.escape(item["summary"] or item["entity_id"])
                url = item["evidence_urls"][0] if item.get("evidence_urls") else ""
                lbl = _html.escape(item["entity_id"] or item["entity_type"])
                link = (f'<a class="link" href="{_html.escape(url)}" target="_blank">{lbl}</a>'
                        if url else f'<span class="lbl">{lbl}</span>')
                parts.append(
                    f'<li><div class="node"><span class="caret leaf">▸</span>'
                    f'{link} <span class="desc">{summary}</span> '
                    f'<span class="badge {bcss}">{blabel}</span></div></li>')
        parts.append('</ul>')
        parts.append('</li>')
    parts.append('</ul>')
    return "\n".join(parts)


def render_html(tree: dict) -> str:
    """Reuse the original map's CSS/visual shell, swap in the generated tree."""
    shell = _load_shell()
    body = _tree_ul(tree)
    generated = tree["generated_at"]
    # Replace the shell's <ul class="tree" ...> ... </ul> with our generated body.
    start = shell.find('<ul class="tree"')
    end = shell.find("</ul>\n</main>")
    if start != -1 and end != -1:
        shell = shell[:start] + body + "\n" + shell[end + len("</ul>"):]
    # Update the refresh pill so it reads as ledger-derived.
    shell = shell.replace(
        "Last refresh: Jul 8, 2026",
        f"Auto-generated from eva-state ledger: {generated}")
    return shell


def _load_shell() -> str:
    if os.path.exists(SHELL_HTML):
        with open(SHELL_HTML, "r", encoding="utf-8") as fh:
            return fh.read()
    # Minimal fallback shell if the source HTML isn't bundled.
    return (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        "<title>EVA — Project Map (generated)</title>"
        "<style>body{background:#07090d;color:#e6edf3;font-family:sans-serif}"
        ".badge{font-size:10px;padding:2px 8px;border-radius:20px}"
        ".b-live{color:#4ade80}.b-prog{color:#60a5fa}.b-open{color:#fbbf24}"
        ".b-plan{color:#6b7280}.b-block{color:#ff6b6b}.desc{color:#8b97a7}"
        "ul.tree ul{padding-left:22px}</style></head><body><main>"
        '<h1>EVA — Project Map (Last refresh: Jul 8, 2026)</h1>'
        '<ul class="tree" id="root"></ul>\n</main>'
        "<script>function tog(e){}</script></body></html>")


__all__ = ["build_tree", "render", "render_html", "JSON_PATH", "HTML_PATH"]
