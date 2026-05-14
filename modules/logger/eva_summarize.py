#!/usr/bin/env python3
"""
eva_summarize.py — EVA Daily Summary Generator
Module 1 of EVA's architecture.

Generates a human-readable + structured summary for a given day.
Can be run at end of day (via cron) or on demand.

Usage:
    python eva_summarize.py                  # Summarise today
    python eva_summarize.py --date 2026-05-14  # Specific date
    python eva_summarize.py --print            # Print to stdout only (no file save)
"""

import json
import sys
import argparse
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

DATA_DIR = Path.home() / "eva-data"
ACTIVITY_DIR = DATA_DIR / "activity"
SUMMARIES_DIR = DATA_DIR / "summaries"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVA-SUMMARY] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("eva_summarize")

# ─────────────────────────────────────────────
# App category mapping
# ─────────────────────────────────────────────

# Maps lowercase substrings in app names → category
APP_CATEGORIES: Dict[str, str] = {
    # Coding / IDE
    "cursor": "coding",
    "code": "coding",
    "vscode": "coding",
    "vim": "coding",
    "neovim": "coding",
    "nvim": "coding",
    "emacs": "coding",
    "pycharm": "coding",
    "intellij": "coding",
    "xcode": "coding",
    "terminal": "coding",
    "iterm": "coding",
    "alacritty": "coding",
    "kitty": "coding",
    "hyper": "coding",
    "warp": "coding",
    "bash": "coding",
    "zsh": "coding",
    "python": "coding",
    "node": "coding",
    "java": "coding",

    # Browsing
    "chrome": "browsing",
    "firefox": "browsing",
    "safari": "browsing",
    "edge": "browsing",
    "brave": "browsing",
    "opera": "browsing",
    "arc": "browsing",
    "chromium": "browsing",
    "vivaldi": "browsing",

    # Communication
    "slack": "communication",
    "discord": "communication",
    "zoom": "communication",
    "teams": "communication",
    "mail": "communication",
    "outlook": "communication",
    "gmail": "communication",
    "telegram": "communication",
    "whatsapp": "communication",
    "messages": "communication",
    "notion": "communication",
    "linear": "communication",
    "jira": "communication",

    # Productivity / Documents
    "word": "productivity",
    "excel": "productivity",
    "powerpoint": "productivity",
    "numbers": "productivity",
    "pages": "productivity",
    "keynote": "productivity",
    "figma": "productivity",
    "sketch": "productivity",
    "affinity": "productivity",
    "photoshop": "productivity",
    "finder": "productivity",
    "explorer": "productivity",
    "obsidian": "productivity",
    "bear": "productivity",
    "roam": "productivity",
    "logseq": "productivity",
}

CATEGORY_ORDER = ["coding", "browsing", "communication", "productivity", "other"]


def categorize_app(app_name: str) -> str:
    """Return the category for an app name."""
    lower = app_name.lower()
    for keyword, category in APP_CATEGORIES.items():
        if keyword in lower:
            return category
    return "other"


# ─────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────

def load_events(target_date: date) -> List[dict]:
    path = ACTIVITY_DIR / f"{target_date.isoformat()}.jsonl"
    if not path.exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


# ─────────────────────────────────────────────
# Analysis functions
# ─────────────────────────────────────────────

def compute_app_time(events: List[dict]) -> Dict[str, float]:
    totals: Dict[str, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            app = ev.get("app_name", "unknown")
            totals[app] += ev.get("duration_seconds", 0)
    return dict(totals)


def compute_category_time(app_time: Dict[str, float]) -> Dict[str, float]:
    category_totals: Dict[str, float] = defaultdict(float)
    for app, secs in app_time.items():
        cat = categorize_app(app)
        category_totals[cat] += secs
    return dict(category_totals)


def compute_focus_score(events: List[dict], total_active_seconds: float) -> int:
    """Focus score 0–100."""
    if total_active_seconds < 60:
        return 0
    focus_events = [ev for ev in events if ev.get("event_type") == "window_focus"]
    context_switches = len(focus_events)
    active_hours = total_active_seconds / 3600
    switches_per_hour = context_switches / active_hours if active_hours > 0 else 0
    switch_penalty = min(50, switches_per_hour * 2)
    deep_blocks = sum(1 for ev in focus_events if ev.get("duration_seconds", 0) > 1800)
    deep_bonus = min(30, deep_blocks * 10)
    return max(0, min(100, int(100 - switch_penalty + deep_bonus - 20)))


def find_longest_focus_block(events: List[dict]) -> Optional[dict]:
    """Return the window_focus event with the longest duration."""
    focus_events = [ev for ev in events if ev.get("event_type") == "window_focus"]
    if not focus_events:
        return None
    return max(focus_events, key=lambda ev: ev.get("duration_seconds", 0))


def extract_sessions(events: List[dict], gap_minutes: float = 15) -> List[dict]:
    focus_events = [ev for ev in events if ev.get("event_type") == "window_focus"]
    if not focus_events:
        return []

    sessions = []
    session_start = None
    session_end = None
    session_apps: Dict[str, float] = defaultdict(float)
    last_ts = None

    for ev in focus_events:
        try:
            ts = datetime.fromisoformat(ev["timestamp"])
        except (KeyError, ValueError):
            continue
        dur = ev.get("duration_seconds", 0)
        app = ev.get("app_name", "unknown")

        if session_start is None:
            session_start = ts
            session_end = ts + timedelta(seconds=dur)
            session_apps[app] += dur
            last_ts = session_end
            continue

        gap = (ts - last_ts).total_seconds()
        if gap > gap_minutes * 60:
            primary = max(session_apps, key=session_apps.get)
            sessions.append({
                "start": session_start.strftime("%H:%M"),
                "end": session_end.strftime("%H:%M"),
                "duration_minutes": round((session_end - session_start).total_seconds() / 60, 1),
                "primary_app": primary,
            })
            session_start = ts
            session_apps = defaultdict(float)

        session_end = ts + timedelta(seconds=dur)
        session_apps[app] += dur
        last_ts = session_end

    if session_start and session_end:
        primary = max(session_apps, key=session_apps.get) if session_apps else "unknown"
        sessions.append({
            "start": session_start.strftime("%H:%M"),
            "end": session_end.strftime("%H:%M"),
            "duration_minutes": round((session_end - session_start).total_seconds() / 60, 1),
            "primary_app": primary,
        })

    return sessions


def generate_eva_insight(summary: dict) -> str:
    """One-sentence EVA observation about the day."""
    score = summary.get("focus_score", 0)
    switches = summary.get("context_switches", 0)
    top_apps = summary.get("top_apps", [])
    sessions = summary.get("work_sessions", [])
    longest = summary.get("longest_focus_block_minutes", 0)

    best = max(sessions, key=lambda s: s["duration_minutes"], default=None)
    top_app = top_apps[0]["app"] if top_apps else "unknown"
    top_cat = summary.get("top_category", "unknown")

    if best and best["duration_minutes"] >= 30:
        block_str = f"best block was {best['start']}–{best['end']} ({best['duration_minutes']} min in {best['primary_app']})"
    else:
        block_str = f"no extended focus blocks today"

    quality = (
        "strong focus day" if score >= 75
        else "moderate focus day" if score >= 50
        else "fragmented day — many context switches"
    )

    return (
        f"A {quality} (score {score}/100): {block_str}; "
        f"{switches} context switches, "
        f"most time in {top_cat} ({top_app})."
    )


# ─────────────────────────────────────────────
# Summary builder
# ─────────────────────────────────────────────

def build_summary(target_date: date) -> dict:
    """Build the full structured summary for a date."""
    events = load_events(target_date)

    if not events:
        return {
            "date": target_date.isoformat(),
            "total_active_minutes": 0,
            "focus_score": 0,
            "top_apps": [],
            "top_category": "none",
            "category_breakdown": {},
            "work_sessions": [],
            "context_switches": 0,
            "idle_periods": 0,
            "longest_focus_block_minutes": 0,
            "longest_focus_block_app": "none",
            "peak_focus_hour": "unknown",
            "eva_insight": "No activity data found for this day.",
        }

    app_time = compute_app_time(events)
    total_active_seconds = sum(app_time.values())
    total_active_minutes = round(total_active_seconds / 60, 1)

    # Top apps
    top_apps = [
        {
            "app": app,
            "minutes": round(secs / 60, 1),
            "percentage": round((secs / total_active_seconds) * 100, 1) if total_active_seconds > 0 else 0,
        }
        for app, secs in sorted(app_time.items(), key=lambda x: -x[1])
    ]

    # Categories
    cat_time = compute_category_time(app_time)
    category_breakdown = {
        cat: round(cat_time.get(cat, 0) / 60, 1)
        for cat in CATEGORY_ORDER
    }
    top_category = max(cat_time, key=cat_time.get) if cat_time else "none"

    # Sessions
    work_sessions = extract_sessions(events)

    # Scores & stats
    focus_score = compute_focus_score(events, total_active_seconds)
    context_switches = sum(1 for ev in events if ev.get("event_type") == "window_focus")
    idle_periods = sum(1 for ev in events if ev.get("event_type") == "idle_start")

    # Longest focus block
    longest_ev = find_longest_focus_block(events)
    longest_minutes = round(longest_ev["duration_seconds"] / 60, 1) if longest_ev else 0
    longest_app = longest_ev.get("app_name", "none") if longest_ev else "none"

    # Peak focus hour
    hourly: Dict[int, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            try:
                ts = datetime.fromisoformat(ev["timestamp"])
                hourly[ts.hour] += ev.get("duration_seconds", 0)
            except (KeyError, ValueError):
                pass
    peak_hour = f"{max(hourly, key=hourly.get):02d}:00" if hourly else "unknown"

    summary = {
        "date": target_date.isoformat(),
        "total_active_minutes": total_active_minutes,
        "focus_score": focus_score,
        "top_apps": top_apps[:10],
        "top_category": top_category,
        "category_breakdown": category_breakdown,
        "work_sessions": work_sessions,
        "context_switches": context_switches,
        "idle_periods": idle_periods,
        "longest_focus_block_minutes": longest_minutes,
        "longest_focus_block_app": longest_app,
        "peak_focus_hour": peak_hour,
        "eva_insight": "",  # filled next
    }
    summary["eva_insight"] = generate_eva_insight(summary)
    return summary


def save_summary(summary: dict) -> Path:
    """Write summary JSON to ~/eva-data/summaries/YYYY-MM-DD.json."""
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    path = SUMMARIES_DIR / f"{summary['date']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path


# ─────────────────────────────────────────────
# Human-readable report
# ─────────────────────────────────────────────

def print_report(summary: dict):
    """Print a clean human-readable report to stdout."""
    width = 60
    sep = "═" * width
    thin = "─" * width

    print(f"\n{sep}")
    print(f"  EVA DAILY SUMMARY — {summary['date']}")
    print(sep)

    print(f"\n  Total active time  : {summary['total_active_minutes']} minutes")
    print(f"  Focus score        : {summary['focus_score']} / 100")
    print(f"  Context switches   : {summary['context_switches']}")
    print(f"  Idle periods       : {summary['idle_periods']}")
    print(f"  Peak focus hour    : {summary['peak_focus_hour']}")
    print(f"  Longest block      : {summary['longest_focus_block_minutes']} min ({summary['longest_focus_block_app']})")

    print(f"\n{thin}")
    print("  TIME BY CATEGORY")
    print(thin)
    for cat, mins in summary["category_breakdown"].items():
        bar_len = int((mins / max(summary["total_active_minutes"], 1)) * 30)
        bar = "█" * bar_len
        print(f"  {cat:15s} {mins:6.1f} min  {bar}")

    print(f"\n{thin}")
    print("  TOP APPS")
    print(thin)
    for item in summary["top_apps"][:8]:
        bar_len = int((item["percentage"] / 100) * 30)
        bar = "█" * bar_len
        print(f"  {item['app']:20s} {item['minutes']:6.1f} min  {item['percentage']:5.1f}%  {bar}")

    if summary["work_sessions"]:
        print(f"\n{thin}")
        print("  WORK SESSIONS")
        print(thin)
        for s in summary["work_sessions"]:
            print(f"  {s['start']}–{s['end']:5s}  {s['duration_minutes']:5.1f} min  [{s['primary_app']}]")

    print(f"\n{thin}")
    print("  EVA INSIGHT")
    print(thin)
    # Word-wrap the insight at ~55 chars
    words = summary["eva_insight"].split()
    line = "  "
    for word in words:
        if len(line) + len(word) + 1 > 57:
            print(line)
            line = "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)

    print(f"\n{sep}\n")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EVA Daily Summary Generator")
    parser.add_argument(
        "--date",
        help="Date to summarise (YYYY-MM-DD). Defaults to today.",
        default=None,
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print to stdout only, don't save to file.",
    )
    args = parser.parse_args()

    # Parse target date
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            log.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    log.info(f"Building summary for {target_date.isoformat()}")
    summary = build_summary(target_date)

    print_report(summary)

    if not args.print_only:
        path = save_summary(summary)
        log.info(f"Summary saved to: {path}")
    else:
        log.info("Print-only mode — summary not saved.")


if __name__ == "__main__":
    main()
