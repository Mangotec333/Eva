"""
EVA Agent Builder — the meta-agent that builds agents.

Three capabilities, mirroring the way every other Eva module is shaped
(connector/introspection + store + gate/CLI + launcher routes):

  1. ``catalog()``  — inventory every existing agent/module by scanning
     ``modules/`` on disk: entrypoint, port, launchd trigger, README, status.
     Optionally rewrites ``EVA_AGENT_CATALOG.md`` so the roster stays current.
  2. ``scaffold(name, ...)`` — stand up a brand-new agent/module following the
     canonical Eva pattern (store.py + <slug>.py connector + gate + cli.py +
     README) so a missing capability can be filled in minutes, not hours.
  3. ``capture(...)`` — take a one-off workflow Eva/PC just performed
     (explainer-video build, Apollo outreach, content cards, …) and persist it
     as a REPEATABLE SOP + a Markdown runbook, so EVA can do it autonomously
     next time.

Design constraints (match the repo):
  * Stdlib only — os, json, re, sqlite3, pathlib, urllib. No pip installs.
  * Never hardcode secrets. Slack notification is best-effort and reuses the
    social-publish ``slack_client`` (token from env) when present.
  * Fail safe — a missing optional dep or Slack token never raises; it degrades.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import store

# ── Locating the Eva repo root ──────────────────────────────────────────────
# Works whether invoked from the module dir, the launcher, or an SOP runner.


def eva_home() -> Path:
    env = os.environ.get("EVA_HOME")
    if env and (Path(env) / "modules").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "modules").is_dir():
            return parent
    return Path.home() / "Eva"


EVA_HOME = eva_home()
MODULES_DIR = EVA_HOME / "modules"
CATALOG_PATH = EVA_HOME / "EVA_AGENT_CATALOG.md"

# Non-agent / tooling dirs we skip when inventorying.
_SKIP_DIRS = {"autostart", "command-center", "morning-os"}

_PORT_RE = re.compile(r"\b(?:PORT|port)\s*=\s*(\d{3,5})\b")
_UVICORN_RE = re.compile(r"port\s*=\s*(\d{3,5})")


# ── Slack (best-effort, reuses social-publish client) ───────────────────────

def _notify_slack(text: str) -> dict:
    """Post a build notification to the founder DM. Never raises."""
    social_dir = MODULES_DIR / "social-publish"
    import sys
    if str(social_dir) not in sys.path:
        sys.path.insert(0, str(social_dir))
    try:
        import slack_client  # noqa: PLC0415
    except Exception as exc:
        return {"ok": False, "error": f"slack_client unavailable: {exc}"}
    if not slack_client.is_configured():
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set — skipped"}
    return slack_client.post_message(text, channel=slack_client.DEFAULT_REVIEW_CHANNEL)


# ── 1. Catalog / inventory ──────────────────────────────────────────────────

def _detect_entrypoint(mod_dir: Path) -> str:
    """Pick the most likely entrypoint file for a module."""
    candidates = ["main.py", f"{mod_dir.name}.py",
                  f"{mod_dir.name.replace('-', '_')}.py",
                  "service.py", "cli.py"]
    for name in candidates:
        if (mod_dir / name).is_file():
            return name
    # first *_api.py / *_agent.py / sentinel-style file
    for p in sorted(mod_dir.glob("*.py")):
        if p.name.endswith(("_api.py", "_agent.py", "_bridge.py")):
            return p.name
    pys = sorted(p.name for p in mod_dir.glob("*.py"))
    return pys[0] if pys else ""


def _detect_port(entry: Path) -> int | None:
    if not entry.is_file():
        return None
    try:
        text = entry.read_text(errors="ignore")
    except OSError:
        return None
    for rx in (_PORT_RE, _UVICORN_RE):
        m = rx.search(text)
        if m:
            return int(m.group(1))
    return None


def _detect_launchd(mod_dir: Path) -> list[str]:
    plists = list(mod_dir.glob("launchd/*.plist")) + list(mod_dir.glob("*.plist"))
    return [p.name for p in plists]


def _detect_readme(mod_dir: Path) -> str:
    for p in mod_dir.glob("README*"):
        return p.name
    return ""


def _detect_status(mod_dir: Path) -> str:
    if (mod_dir / "DEPRECATED.md").is_file():
        return "deprecated"
    return "active"


def inspect_module(mod_dir: Path) -> dict:
    entry = _detect_entrypoint(mod_dir)
    entry_path = mod_dir / entry if entry else mod_dir
    return {
        "name": mod_dir.name,
        "entrypoint": entry,
        "port": _detect_port(entry_path),
        "launchd": _detect_launchd(mod_dir),
        "readme": _detect_readme(mod_dir),
        "status": _detect_status(mod_dir),
        "path": str(mod_dir.relative_to(EVA_HOME)),
    }


def catalog(write: bool = False) -> dict:
    """Inventory every agent/module under modules/.

    Returns {count, agents:[...]}. With ``write=True`` also refreshes the
    machine-generated section of EVA_AGENT_CATALOG.md.
    """
    agents = []
    if MODULES_DIR.is_dir():
        for mod_dir in sorted(MODULES_DIR.iterdir()):
            if not mod_dir.is_dir() or mod_dir.name in _SKIP_DIRS:
                continue
            if mod_dir.name.startswith((".", "_")):
                continue
            # angels/ holds sub-agents — descend one level.
            if mod_dir.name == "angels":
                for sub in sorted(mod_dir.iterdir()):
                    if sub.is_dir():
                        agents.append(inspect_module(sub))
                continue
            agents.append(inspect_module(mod_dir))

    result = {"count": len(agents), "agents": agents,
              "generated_at": store._now(), "eva_home": str(EVA_HOME)}

    if write:
        result["catalog_written"] = _write_catalog_snapshot(agents)
    return result


def _write_catalog_snapshot(agents: list[dict]) -> str:
    """Write/refresh a machine-generated inventory table.

    Keeps the human-authored prose in EVA_AGENT_CATALOG.md intact by writing
    the auto section between clearly marked fences; if the file is absent it is
    created fresh.
    """
    begin = "<!-- AGENT-BUILDER:AUTO-INVENTORY:BEGIN -->"
    end = "<!-- AGENT-BUILDER:AUTO-INVENTORY:END -->"

    lines = [begin,
             f"### Auto-inventory (generated {store._now()})",
             "",
             "| Module | Entrypoint | Port | Trigger | Status |",
             "|---|---|---|---|---|"]
    for a in agents:
        trigger = "launchd" if a["launchd"] else ("route/HTTP" if a["port"] else "cli/manual")
        port = a["port"] if a["port"] is not None else "—"
        lines.append(f"| {a['name']} | `{a['entrypoint'] or '—'}` | {port} | {trigger} | {a['status']} |")
    lines.append(end)
    block = "\n".join(lines)

    existing = CATALOG_PATH.read_text() if CATALOG_PATH.exists() else ""
    if begin in existing and end in existing:
        pre = existing.split(begin)[0]
        post = existing.split(end)[1]
        new = pre + block + post
    elif existing:
        new = existing.rstrip() + "\n\n## Auto-inventory\n\n" + block + "\n"
    else:
        new = "# EVA Agent Catalog\n\n" + block + "\n"
    CATALOG_PATH.write_text(new)
    return str(CATALOG_PATH)


# ── 2. Scaffold a new agent/module ──────────────────────────────────────────

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "new-agent"


def scaffold(name: str, purpose: str = "", port: int | None = None,
             with_launchd: bool = False, notify: bool = False) -> dict:
    """Create modules/<slug>/ with the canonical Eva agent skeleton.

    Files: store.py, <module>.py (connector/core), gate.py, cli.py, README.
    Optionally a launchd plist. Refuses to overwrite an existing module.
    """
    slug = slugify(name)
    mod_name = slug.replace("-", "_")
    mod_dir = MODULES_DIR / slug
    if mod_dir.exists():
        return {"ok": False, "error": f"module already exists: {mod_dir.relative_to(EVA_HOME)}"}

    mod_dir.mkdir(parents=True)
    files: list[str] = []

    ctx = {"name": name, "slug": slug, "mod": mod_name,
           "purpose": purpose or f"{name} agent for Eva.",
           "port": port, "Title": name}

    written = {
        "store.py": _tmpl_store(ctx),
        f"{mod_name}.py": _tmpl_core(ctx),
        "gate.py": _tmpl_gate(ctx),
        "cli.py": _tmpl_cli(ctx),
        f"README_{mod_name}.md": _tmpl_readme(ctx),
        "requirements.txt": "# stdlib-only; add third-party deps here if needed\n",
        ".gitignore": "*.db\n__pycache__/\n",
    }
    for fname, content in written.items():
        (mod_dir / fname).write_text(content)
        files.append(f"{slug}/{fname}")

    if with_launchd:
        (mod_dir / "launchd").mkdir(exist_ok=True)
        plist = _tmpl_plist(ctx)
        (mod_dir / "launchd" / f"com.eva.{slug}.plist").write_text(plist)
        files.append(f"{slug}/launchd/com.eva.{slug}.plist")

    rec = store.record_scaffold(name, slug, port, ctx["purpose"], files)

    routes = [f"/{slug}/health", f"/{slug}/run"]
    if notify:
        _notify_slack(
            f"🛠️ *Agent Builder scaffolded a new agent*: `{slug}`\n"
            f"Purpose: {ctx['purpose']}\n"
            f"Files: {len(files)} • Suggested launcher routes: {', '.join(routes)}"
        )

    return {"ok": True, "slug": slug, "module_dir": str(mod_dir.relative_to(EVA_HOME)),
            "files": files, "suggested_routes": routes, "scaffold_id": rec["id"],
            "next_steps": [
                f"Implement the TODOs in modules/{slug}/{mod_name}.py",
                f"Wire launcher routes ({', '.join(routes)}) in modules/launcher/eva_launcher.py",
                "Run `python cli.py catalog --write` to refresh EVA_AGENT_CATALOG.md",
            ]}


# ── 3. Capture a one-off workflow as a repeatable SOP ───────────────────────

def capture(name: str, steps: list[str], trigger: str = "manual",
            summary: str = "", inputs: list[str] | None = None,
            module: str = "", notify: bool = False) -> dict:
    """Persist a one-off workflow as a repeatable SOP + a Markdown runbook.

    The SOP row lets EVA re-run the process; the runbook is a human/agent-
    readable checklist saved under docs/sops/ (or inside a module if given).
    """
    inputs = inputs or []
    slug = slugify(name)
    sop_dir = (MODULES_DIR / module / "sops") if module else (EVA_HOME / "docs" / "sops")
    sop_dir.mkdir(parents=True, exist_ok=True)
    sop_path = sop_dir / f"{slug}.md"
    sop_path.write_text(_tmpl_sop(name, slug, trigger, summary, steps, inputs))

    rec = store.record_sop(name, slug, trigger, summary, steps, inputs,
                           module=module, sop_path=str(sop_path.relative_to(EVA_HOME)))

    if notify:
        _notify_slack(
            f"📋 *Agent Builder captured a repeatable SOP*: `{slug}`\n"
            f"Trigger: {trigger} • Steps: {len(steps)}\n"
            f"Runbook: {rec['sop_path']}"
        )

    return {"ok": True, "sop_id": rec["id"], "slug": slug,
            "sop_path": rec["sop_path"], "steps": len(steps), "trigger": trigger}


# ── Templates (kept inline so the module is self-contained, stdlib-only) ─────

def _tmpl_store(ctx: dict) -> str:
    return f'''"""
{ctx["name"]} — SQLite persistence. Auto-generated by Eva Agent Builder.
State survives restarts; the DB is gitignored (*.db). Stdlib only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "{ctx["mod"].upper()}_DB",
    os.path.join(os.path.dirname(__file__), "{ctx["mod"]}.db"),
)

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id          TEXT PRIMARY KEY,
                payload     TEXT NOT NULL DEFAULT '{{}}',
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()


def create(payload: dict) -> dict:
    init_db()
    rid = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO records (id, payload, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (rid, json.dumps(payload), STATUS_PENDING, now, now),
        )
        conn.commit()
    return get(rid)


def get(rid: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d.get("payload") or "{{}}")
        return d


def list_all(status: str | None = None) -> list[dict]:
    init_db()
    with _connect() as conn:
        if status:
            cur = conn.execute("SELECT * FROM records WHERE status=? ORDER BY created_at DESC", (status,))
        else:
            cur = conn.execute("SELECT * FROM records ORDER BY created_at DESC")
        out = []
        for row in cur.fetchall():
            d = dict(row)
            d["payload"] = json.loads(d.get("payload") or "{{}}")
            out.append(d)
        return out
'''


def _tmpl_core(ctx: dict) -> str:
    return f'''"""
{ctx["name"]} — core logic. Auto-generated by Eva Agent Builder.

{ctx["purpose"]}

Follow the Eva pattern: this module holds the domain work; ``gate.py`` handles
approval/side-effects; ``cli.py`` is the operator entrypoint; the launcher
exposes HTTP routes that delegate here. Stdlib only — never hardcode secrets
(read them from os.environ).
"""

from __future__ import annotations

import os

import store


def creds_status() -> dict:
    """Report credential availability without returning secrets."""
    # TODO: replace with the env vars this agent actually needs.
    needed = []  # e.g. ["{ctx["mod"].upper()}_API_KEY"]
    missing = [k for k in needed if not os.environ.get(k)]
    return {{"configured": not missing, "missing_env": missing}}


def run(payload: dict | None = None) -> dict:
    """Do the agent's work once. TODO: implement the real behaviour."""
    payload = payload or {{}}
    rec = store.create(payload)
    # TODO: perform the actual task here and update the record status.
    return {{"ok": True, "record_id": rec["id"], "status": rec["status"],
            "note": "scaffold stub — implement {ctx["mod"]}.run()"}}
'''


def _tmpl_gate(ctx: dict) -> str:
    return f'''"""
{ctx["name"]} — approve-then-act gate. Auto-generated by Eva Agent Builder.

Mirrors modules/social-publish/gate.py: nothing with an external side-effect
runs without explicit approval (Slack ✅ / `approve`, or a launcher endpoint).
Slack notification reuses modules/social-publish/slack_client.py when present;
its absence is non-fatal.
"""

from __future__ import annotations

import os
import sys

import store

_SOCIAL_DIR = os.path.join(os.path.dirname(__file__), "..", "social-publish")
if os.path.abspath(_SOCIAL_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SOCIAL_DIR))


def _slack():
    try:
        import slack_client  # noqa: PLC0415
        return slack_client
    except Exception:
        return None


def submit_for_approval(payload: dict) -> dict:
    """Record work as pending and post it to Slack for review. No side-effects."""
    rec = store.create(payload)
    sc = _slack()
    slack = {{"ok": False, "error": "slack unavailable"}}
    if sc and sc.is_configured():
        slack = sc.post_message(
            f"*{ctx["name"]}* pending approval (id `{{rec['id']}}`). "
            f"Reply `approve` or react :white_check_mark: to proceed.",
            channel=sc.DEFAULT_REVIEW_CHANNEL,
        )
    return {{"ok": True, "record": rec, "slack": slack}}


def approve(rid: str, actor: str = "cli", via: str = "cli") -> dict:
    """Approve a pending record and act on it. Idempotent."""
    import {ctx["mod"]} as core  # noqa: PLC0415
    rec = store.get(rid)
    if not rec:
        return {{"ok": False, "error": f"record {{rid}} not found"}}
    if rec["status"] == store.STATUS_DONE:
        return {{"ok": True, "noop": True, "record": rec}}
    result = core.run(rec["payload"])
    return {{"ok": True, "actor": actor, "via": via, "result": result}}
'''


def _tmpl_cli(ctx: dict) -> str:
    return f'''#!/usr/bin/env python3
"""
{ctx["name"]} — CLI. Auto-generated by Eva Agent Builder.

Examples:
  python cli.py creds
  python cli.py run   [--json '{{"k":"v"}}']
  python cli.py submit --json '{{"k":"v"}}'
  python cli.py approve <record_id>
  python cli.py list  [--status pending]
"""

from __future__ import annotations

import argparse
import json

import gate
import store
import {ctx["mod"]} as core


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="{ctx["name"]}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("creds", help="show credential status")

    p_run = sub.add_parser("run", help="run the agent once")
    p_run.add_argument("--json", default="{{}}")

    p_sub = sub.add_parser("submit", help="submit work for Slack approval")
    p_sub.add_argument("--json", default="{{}}")

    p_ap = sub.add_parser("approve", help="approve + act on a record")
    p_ap.add_argument("record_id")

    p_ls = sub.add_parser("list", help="list records")
    p_ls.add_argument("--status", default=None)

    args = p.parse_args()

    if args.cmd == "creds":
        _print(core.creds_status())
    elif args.cmd == "run":
        _print(core.run(json.loads(args.json)))
    elif args.cmd == "submit":
        _print(gate.submit_for_approval(json.loads(args.json)))
    elif args.cmd == "approve":
        _print(gate.approve(args.record_id))
    elif args.cmd == "list":
        _print(store.list_all(status=args.status))


if __name__ == "__main__":
    main()
'''


def _tmpl_readme(ctx: dict) -> str:
    port_line = f"\n- **Port:** {ctx['port']}" if ctx["port"] else ""
    return f'''# {ctx["name"]}

> Auto-generated by the Eva Agent Builder. {ctx["purpose"]}

```
{ctx["mod"]}.py   core logic (the domain work)
store.py       sqlite persistence (survives restarts; *.db gitignored)
gate.py        approve-then-act gate (Slack ✅ / launcher endpoint)
cli.py         operator entrypoint
```
{port_line}

## Wiring into the launcher

Add these routes to `modules/launcher/eva_launcher.py` (delegate, import lazily):

| Route | Purpose |
|-------|---------|
| `GET  /{ctx["slug"]}/health` | liveness |
| `POST /{ctx["slug"]}/run` | run the agent once |
| `POST /{ctx["slug"]}/approve/{{id}}` | approve a pending record |

## Credentials

Read from `os.environ` — never hardcode secrets. See `creds_status()` in
`{ctx["mod"]}.py` for the exact env vars this agent needs.

## Next steps

1. Implement the TODOs in `{ctx["mod"]}.py`.
2. Wire the launcher routes above.
3. Run `python ../agent-builder/cli.py catalog --write` to refresh the roster.
'''


def _tmpl_plist(ctx: dict) -> str:
    port = ctx["port"] or ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.eva.{ctx["slug"]}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>{ctx["mod"]}.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH/modules/{ctx["slug"]}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH/logs/{ctx["slug"]}.out.log</string>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH/logs/{ctx["slug"]}.error.log</string>
    <!-- port {port} -->
</dict>
</plist>
'''


def _tmpl_sop(name: str, slug: str, trigger: str, summary: str,
              steps: list[str], inputs: list[str]) -> str:
    step_lines = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) or "1. (no steps recorded)"
    input_lines = "\n".join(f"- {i}" for i in inputs) or "- (none)"
    return f'''# SOP — {name}

> Captured by the Eva Agent Builder so EVA can repeat this autonomously.
> **Trigger:** {trigger}

## Summary

{summary or "(none provided)"}

## Inputs required

{input_lines}

## Steps

{step_lines}

## Automation notes

- Slug: `{slug}`
- To turn this SOP into a standalone agent:
  `python modules/agent-builder/cli.py scaffold --name "{name}"`
- Re-run / audit captured SOPs: `python modules/agent-builder/cli.py sops`
'''
