#!/usr/bin/env python3
"""
EVA Landing + Interest Tracker
==============================

Two signals about the Eva acquisition funnel, in one place:

1. **Landing page liveness** — an HTTP HEAD (GET fallback) against each public
   landing page and its lead-magnet routes. Reports live/down + the HTTP code.

2. **Per-magnet interest** — GoHighLevel contact counts, one per magnet tag,
   plus the total ``eva-acquisition-lead`` count. Counting routes through the
   *existing* GHL client (``modules/ghl-agent/ghl_client.py``) so the token is
   read from the same ``GHL_ACCESS_TOKEN`` / ``GHL_LOCATION_ID`` env the
   ghl-agent uses — nothing is hardcoded here.

Offline (no ``GHL_ACCESS_TOKEN``) the tracker still reports landing liveness and
falls back to the in-memory stub for counts, so it never hard-fails.

Usage:
  python3 landing_tracker.py            # human-readable report
  python3 landing_tracker.py --json     # machine-readable JSON (also cached)
  python3 landing_tracker.py --text      # morning-brief "LANDING + INTEREST" block

The JSON is cached to ``~/Eva/logs/status/landing_tracker.json`` on every run so
the launcher (:8768 /landing_status) and the command center can read it cheaply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The GHL client lives in the ghl-agent module. Import it directly (it only pulls
# stdlib) rather than re-implementing GHL auth here.
_GHL_AGENT_DIR = Path(__file__).resolve().parent.parent / "ghl-agent"
if str(_GHL_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_GHL_AGENT_DIR))

# GHL location for the Eva acquisition sub-account (public; the *token* is the
# secret and is read from the env by the client, never hardcoded).
DEFAULT_LOCATION_ID = "kyK4yAY6Hur3F4deCx2n"

BASE_URL = "https://eva-acquisition.mangotec.ai"

# name → path. name is what shows up in the report / brief.
LANDING_PAGES = [
    ("Home", "/"),
    ("Whitepaper", "/whitepaper"),
    ("Digest", "/digest"),
    ("Scorecard", "/scorecard"),
    ("Deal Audit", "/deal-audit"),
]

# label → GHL tag. Order is the report order. The total lead tag is last.
MAGNETS = [
    ("Whitepaper", "eva-magnet-whitepaper"),
    ("Digest", "eva-magnet-digest"),
    ("Scorecard", "eva-magnet-scorecard"),
    ("Deal Audit", "eva-magnet-deal-audit"),
]
TOTAL_TAG = "eva-acquisition-lead"

CACHE_PATH = Path.home() / "Eva" / "logs" / "status" / "landing_tracker.json"

HTTP_TIMEOUT = 8.0


# ---------------------------------------------------------------------------
# Landing liveness
# ---------------------------------------------------------------------------

def check_url(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    """HEAD the URL (GET fallback). Return live/down + HTTP status code."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": "eva-landing-tracker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = resp.status
                return {"live": 200 <= code < 400, "status": code, "error": None}
        except urllib.error.HTTPError as exc:
            # A response with a code (e.g. 405 to HEAD, 403) — the page IS up.
            # For HEAD-rejected pages, fall through to GET; otherwise report it.
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            return {"live": 200 <= exc.code < 400, "status": exc.code, "error": None}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if method == "GET":
                return {"live": False, "status": None, "error": str(getattr(exc, "reason", exc))}
    return {"live": False, "status": None, "error": "unreachable"}


def check_landing() -> list[dict]:
    results = []
    for name, path in LANDING_PAGES:
        url = f"{BASE_URL}{path}"
        r = check_url(url)
        results.append({"name": name, "path": path, "url": url, **r})
    return results


# ---------------------------------------------------------------------------
# Per-magnet interest (GHL contact counts by tag)
# ---------------------------------------------------------------------------

def _build_ghl_client():
    """Build the existing GHL client, honouring the ghl-agent env convention."""
    import ghl_client

    if ghl_client.is_offline():
        return ghl_client.build_client(offline=True), True
    location = os.environ.get("GHL_LOCATION_ID") or DEFAULT_LOCATION_ID
    return ghl_client.HttpGHLClient(location_id=location), False


def check_magnets() -> dict:
    client, offline = _build_ghl_client()
    magnets = []
    for label, tag in MAGNETS:
        res = client.count_contacts_by_tag(tag)
        magnets.append({
            "label": label,
            "tag": tag,
            "count": res.get("count"),
            "ok": res.get("ok", False),
        })
    total_res = client.count_contacts_by_tag(TOTAL_TAG)
    return {
        "offline": offline,
        "magnets": magnets,
        "total": {
            "tag": TOTAL_TAG,
            "count": total_res.get("count"),
            "ok": total_res.get("ok", False),
        },
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def build_report() -> dict:
    landing = check_landing()
    interest = check_magnets()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "location_id": os.environ.get("GHL_LOCATION_ID") or DEFAULT_LOCATION_ID,
        "ghl_offline": interest["offline"],
        "landing": landing,
        "magnets": interest["magnets"],
        "total": interest["total"],
        "summary": {
            "pages_live": sum(1 for p in landing if p["live"]),
            "pages_total": len(landing),
            "total_leads": interest["total"]["count"],
        },
    }
    return report


def write_cache(report: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(report, indent=2))
    except OSError:
        # Caching is best-effort — never fail the report because the log dir
        # isn't writable (e.g. sandbox).
        pass


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _count_str(count) -> str:
    return "—" if count is None else str(count)


def render_text(report: dict) -> str:
    """Compact block for the morning brief 'LANDING + INTEREST' section."""
    lines = ["LANDING + INTEREST"]

    live = report["summary"]["pages_live"]
    total = report["summary"]["pages_total"]
    down = [p["name"] for p in report["landing"] if not p["live"]]
    if down:
        lines.append(f"Pages: {live}/{total} live — DOWN: {', '.join(down)}")
    else:
        lines.append(f"Pages: {live}/{total} live")

    parts = [f"{m['label']} {_count_str(m['count'])}" for m in report["magnets"]]
    lines.append("Interest: " + " · ".join(parts))

    total_leads = report["total"]["count"]
    suffix = " (GHL offline — stub counts)" if report["ghl_offline"] else ""
    lines.append(f"Total leads: {_count_str(total_leads)}{suffix}")
    return "\n".join(lines)


def render_human(report: dict) -> str:
    green, red, dim, cyan, nc = "\033[0;32m", "\033[0;31m", "\033[2m", "\033[0;36m", "\033[0m"
    out = []
    out.append("")
    out.append(f"{cyan}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{nc}")
    out.append(f"{cyan}  EVA LANDING + INTEREST{nc}")
    out.append(f"{cyan}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{nc}")
    out.append("")
    out.append("  Landing pages")
    for p in report["landing"]:
        if p["live"]:
            dot, color, detail = "●", green, f"{p['status']}"
        else:
            dot, color, detail = "○", red, (p.get("error") or f"HTTP {p['status']}")
        out.append(f"  {color}{dot} {p['name']:<12}{nc} {dim}{p['url']}  [{detail}]{nc}")
    out.append("")
    out.append("  Lead-magnet interest (GHL contacts by tag)")
    if report["ghl_offline"]:
        out.append(f"  {dim}(GHL offline — no GHL_ACCESS_TOKEN; showing stub counts){nc}")
    for m in report["magnets"]:
        mark = "" if m["ok"] else f" {dim}(count unavailable){nc}"
        out.append(f"  {cyan}•{nc} {m['label']:<12} {_count_str(m['count']):>6}  {dim}{m['tag']}{nc}{mark}")
    t = report["total"]
    out.append(f"  {cyan}={nc} {'TOTAL':<12} {_count_str(t['count']):>6}  {dim}{t['tag']}{nc}")
    out.append("")
    out.append(f"{cyan}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{nc}")
    out.append(f"  {dim}Generated {report['generated_at']}{nc}")
    out.append(f"  {dim}Cache: {CACHE_PATH}{nc}")
    out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EVA Landing + Interest tracker")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--text", action="store_true",
                        help="emit the morning-brief LANDING + INTEREST block")
    parser.add_argument("--no-cache", action="store_true",
                        help="do not write the cache file")
    args = parser.parse_args(argv)

    report = build_report()
    if not args.no_cache:
        write_cache(report)

    if args.json:
        print(json.dumps(report, indent=2))
    elif args.text:
        print(render_text(report))
    else:
        print(render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
