#!/usr/bin/env python3
"""
eva_context_api.py — EVA Context API Server
Module 1 of EVA's architecture.

Lightweight FastAPI server that reads logged activity data and serves
structured context summaries to EVA and future agents.

Default port: 8765

Usage:
    python eva_context_api.py
    uvicorn eva_context_api:app --port 8765 --reload
"""

import json
import math
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Screenpipe bridge (graceful import)
try:
    from eva_screenpipe_bridge import ScreenpipeBridge
    _screenpipe = ScreenpipeBridge()
except ImportError:
    _screenpipe = None

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

DATA_DIR = Path.home() / "eva-data"
ACTIVITY_DIR = DATA_DIR / "activity"
SUMMARIES_DIR = DATA_DIR / "summaries"
API_PORT = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVA-API] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("eva_context_api")

# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────

app = FastAPI(
    title="EVA Context API",
    description="Serves EVA activity data to AI agents and dashboards. Integrates ActivityWatch, Screenpipe, and built-in logger.",
    version="2.0.0",
)


# ─────────────────────────────────────────────
# Data loading helpers
# ─────────────────────────────────────────────

def load_events_for_date(target_date: date) -> List[dict]:
    """Load all JSONL events for a given date. Returns [] if file missing."""
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


def load_events_range(start: date, end: date) -> List[dict]:
    """Load events for a date range [start, end] inclusive."""
    all_events = []
    current = start
    while current <= end:
        all_events.extend(load_events_for_date(current))
        current += timedelta(days=1)
    return all_events


# ─────────────────────────────────────────────
# Aggregation helpers
# ─────────────────────────────────────────────

def aggregate_app_time(events: List[dict]) -> Dict[str, float]:
    """Sum duration_seconds per app_name for window_focus events."""
    totals: Dict[str, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            app = ev.get("app_name", "unknown")
            totals[app] += ev.get("duration_seconds", 0)
    return dict(totals)


def build_top_apps(app_time: Dict[str, float], total_seconds: float) -> List[dict]:
    """Build sorted top-apps list with percentage."""
    items = sorted(app_time.items(), key=lambda x: -x[1])
    result = []
    for app, secs in items:
        minutes = round(secs / 60, 1)
        pct = round((secs / total_seconds) * 100, 1) if total_seconds > 0 else 0
        result.append({"app": app, "minutes": minutes, "percentage": pct})
    return result


def extract_work_sessions(events: List[dict],
                           gap_minutes: float = 15) -> List[dict]:
    """
    Identify contiguous work blocks by finding gaps > gap_minutes between
    window_focus events. Returns list of session dicts.
    """
    focus_events = [
        ev for ev in events
        if ev.get("event_type") == "window_focus"
    ]
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
            # Start first session
            session_start = ts
            session_end = ts + timedelta(seconds=dur)
            session_apps[app] += dur
            last_ts = session_end
            continue

        gap = (ts - last_ts).total_seconds()
        if gap > gap_minutes * 60:
            # Gap too large — close current session, open new one
            primary = max(session_apps, key=session_apps.get)
            duration_min = round((session_end - session_start).total_seconds() / 60, 1)
            sessions.append({
                "start": session_start.strftime("%H:%M"),
                "end": session_end.strftime("%H:%M"),
                "duration_minutes": duration_min,
                "primary_app": primary,
            })
            session_start = ts
            session_apps = defaultdict(float)

        session_end = ts + timedelta(seconds=dur)
        session_apps[app] += dur
        last_ts = session_end

    # Close final session
    if session_start and session_end:
        primary = max(session_apps, key=session_apps.get) if session_apps else "unknown"
        duration_min = round((session_end - session_start).total_seconds() / 60, 1)
        sessions.append({
            "start": session_start.strftime("%H:%M"),
            "end": session_end.strftime("%H:%M"),
            "duration_minutes": duration_min,
            "primary_app": primary,
        })

    return sessions


def compute_focus_score(events: List[dict], total_active_seconds: float) -> int:
    """
    Focus score 0–100.
    - Higher score = fewer context switches per active hour + longer focus blocks.
    - Context switches > 6/hour reduce score; deep blocks (>30 min) boost it.
    """
    if total_active_seconds < 60:
        return 0

    focus_events = [ev for ev in events if ev.get("event_type") == "window_focus"]
    context_switches = len(focus_events)
    active_hours = total_active_seconds / 3600

    # Baseline: penalise > 6 switches/hour
    switches_per_hour = context_switches / active_hours if active_hours > 0 else 0
    switch_penalty = min(50, switches_per_hour * 2)

    # Reward deep work blocks > 30 minutes
    deep_blocks = sum(
        1 for ev in focus_events
        if ev.get("duration_seconds", 0) > 1800
    )
    deep_bonus = min(30, deep_blocks * 10)

    score = max(0, min(100, int(100 - switch_penalty + deep_bonus - 20)))
    return score


def find_peak_focus_hour(events: List[dict]) -> str:
    """Return the hour (HH:00) with the most accumulated focus time."""
    hourly: Dict[int, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            try:
                ts = datetime.fromisoformat(ev["timestamp"])
                hourly[ts.hour] += ev.get("duration_seconds", 0)
            except (KeyError, ValueError):
                pass
    if not hourly:
        return "unknown"
    peak_hour = max(hourly, key=hourly.get)
    return f"{peak_hour:02d}:00"


def generate_eva_insight(today_summary: dict, patterns: dict = None) -> str:
    """Generate a one-sentence EVA insight based on today's data."""
    sessions = today_summary.get("work_sessions", [])
    top_apps = today_summary.get("top_apps", [])
    switches = today_summary.get("context_switches", 0)
    peak = today_summary.get("peak_focus_hour", "unknown")
    score = today_summary.get("focus_score", 0)

    # Best session
    best_session = max(sessions, key=lambda s: s["duration_minutes"], default=None)
    top_app = top_apps[0]["app"] if top_apps else "unknown"

    if best_session:
        insight = (
            f"Your best focus block was {best_session['start']}–{best_session['end']} "
            f"({best_session['duration_minutes']} min in {best_session['primary_app']}); "
            f"{switches} context switches — "
            + ("within your normal range." if score >= 60 else "higher than your average, consider fewer task hops.")
        )
    else:
        insight = f"No extended focus sessions detected today; top app was {top_app}."

    return insight


# ─────────────────────────────────────────────
# Endpoint helpers
# ─────────────────────────────────────────────

def build_daily_summary(target_date: date) -> dict:
    """Build full summary dict for a given date."""
    events = load_events_for_date(target_date)

    app_time = aggregate_app_time(events)
    total_active_seconds = sum(app_time.values())
    total_active_minutes = round(total_active_seconds / 60, 1)

    top_apps = build_top_apps(app_time, total_active_seconds)
    work_sessions = extract_work_sessions(events)
    focus_score = compute_focus_score(events, total_active_seconds)
    peak_focus_hour = find_peak_focus_hour(events)

    context_switches = sum(
        1 for ev in events if ev.get("event_type") == "window_focus"
    )
    idle_periods = sum(
        1 for ev in events if ev.get("event_type") == "idle_start"
    )

    summary = {
        "date": target_date.isoformat(),
        "total_active_minutes": total_active_minutes,
        "focus_score": focus_score,
        "top_apps": top_apps,
        "work_sessions": work_sessions,
        "context_switches": context_switches,
        "idle_periods": idle_periods,
        "peak_focus_hour": peak_focus_hour,
        "eva_insight": "",  # filled after build
    }
    summary["eva_insight"] = generate_eva_insight(summary)
    return summary


# ─────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "EVA Context API",
        "version": "1.0.0",
        "data_dir": str(DATA_DIR),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/context/today")
def context_today():
    """Today's full activity summary."""
    summary = build_daily_summary(date.today())
    return JSONResponse(content=summary)


@app.get("/context/week")
def context_week():
    """This week's activity summary (Mon–today)."""
    today = date.today()
    # Monday of current week
    start_of_week = today - timedelta(days=today.weekday())
    events = load_events_range(start_of_week, today)

    app_time = aggregate_app_time(events)
    total_active_seconds = sum(app_time.values())

    # Per-day breakdown
    daily = []
    current = start_of_week
    while current <= today:
        day_events = load_events_for_date(current)
        day_app_time = aggregate_app_time(day_events)
        day_active_min = round(sum(day_app_time.values()) / 60, 1)
        day_sessions = extract_work_sessions(day_events)
        day_score = compute_focus_score(day_events, sum(day_app_time.values()))
        daily.append({
            "date": current.isoformat(),
            "active_minutes": day_active_min,
            "focus_score": day_score,
            "sessions": len(day_sessions),
        })
        current += timedelta(days=1)

    return JSONResponse(content={
        "week_start": start_of_week.isoformat(),
        "week_end": today.isoformat(),
        "total_active_minutes": round(total_active_seconds / 60, 1),
        "top_apps": build_top_apps(app_time, total_active_seconds)[:5],
        "daily_breakdown": daily,
        "avg_focus_score": round(
            sum(d["focus_score"] for d in daily) / len(daily), 1
        ) if daily else 0,
    })


@app.get("/context/patterns")
def context_patterns():
    """
    Recurring patterns over the last 30 days:
    - Most used apps
    - Peak focus hours (by day of week)
    - Average session length
    - Average context switches per day
    """
    today = date.today()
    start = today - timedelta(days=29)
    events = load_events_range(start, today)

    # App totals
    app_time = aggregate_app_time(events)
    total_active_seconds = sum(app_time.values())

    # Hourly focus distribution
    hourly_focus: Dict[int, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            try:
                ts = datetime.fromisoformat(ev["timestamp"])
                hourly_focus[ts.hour] += ev.get("duration_seconds", 0)
            except (KeyError, ValueError):
                pass

    # Day-of-week activity
    dow_focus: Dict[int, float] = defaultdict(float)
    for ev in events:
        if ev.get("event_type") == "window_focus":
            try:
                ts = datetime.fromisoformat(ev["timestamp"])
                dow_focus[ts.weekday()] += ev.get("duration_seconds", 0)
            except (KeyError, ValueError):
                pass

    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # Average context switches per day
    days_with_data = set()
    switch_count = 0
    for ev in events:
        if ev.get("event_type") == "window_focus":
            switch_count += 1
            try:
                ts = datetime.fromisoformat(ev["timestamp"])
                days_with_data.add(ts.date().isoformat())
            except (KeyError, ValueError):
                pass

    num_days = max(len(days_with_data), 1)
    avg_switches = round(switch_count / num_days, 1)

    # Average session length
    all_sessions = []
    current = start
    while current <= today:
        day_events = load_events_for_date(current)
        all_sessions.extend(extract_work_sessions(day_events))
        current += timedelta(days=1)

    avg_session_min = (
        round(sum(s["duration_minutes"] for s in all_sessions) / len(all_sessions), 1)
        if all_sessions else 0
    )

    peak_hour = max(hourly_focus, key=hourly_focus.get) if hourly_focus else None
    peak_dow = max(dow_focus, key=dow_focus.get) if dow_focus else None

    return JSONResponse(content={
        "period": f"{start.isoformat()} to {today.isoformat()}",
        "top_apps": build_top_apps(app_time, total_active_seconds)[:8],
        "peak_focus_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "unknown",
        "peak_day_of_week": dow_names[peak_dow] if peak_dow is not None else "unknown",
        "avg_session_length_minutes": avg_session_min,
        "avg_context_switches_per_day": avg_switches,
        "hourly_focus_distribution": {
            f"{h:02d}:00": round(s / 60, 1)
            for h, s in sorted(hourly_focus.items())
        },
        "day_of_week_distribution": {
            dow_names[d]: round(s / 60, 1)
            for d, s in sorted(dow_focus.items())
        },
    })


@app.get("/context/recent")
def context_recent(minutes: int = Query(default=60, ge=1, le=1440)):
    """Last N minutes of activity (default: 60)."""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    events = load_events_for_date(date.today())

    recent = []
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev["timestamp"])
            if ts >= cutoff:
                recent.append(ev)
        except (KeyError, ValueError):
            pass

    app_time = aggregate_app_time(recent)
    total_secs = sum(app_time.values())

    return JSONResponse(content={
        "period_minutes": minutes,
        "since": cutoff.isoformat(timespec="seconds"),
        "event_count": len(recent),
        "active_minutes": round(total_secs / 60, 1),
        "top_apps": build_top_apps(app_time, total_secs)[:5],
        "events": recent[-50:],  # last 50 events max
    })


# ─────────────────────────────────────────────
# Screenpipe Routes
# ─────────────────────────────────────────────

@app.get("/screenpipe/status")
def screenpipe_status():
    """Check if Screenpipe is running and return diagnostic info."""
    if not _screenpipe:
        return JSONResponse(content={"running": False, "message": "Screenpipe bridge not loaded"})
    return JSONResponse(content=_screenpipe.status())


@app.get("/screenpipe/search")
def screenpipe_search(
    q: str = Query(..., description="Search query"),
    content_type: str = Query("all", description="ocr | audio | all"),
    limit: int = Query(20, description="Max results"),
):
    """
    Semantic search across everything EVA has seen and heard.
    Queries Screenpipe's OCR + audio transcript history.

    Example: /screenpipe/search?q=RCFE+investor&content_type=all
    """
    if not _screenpipe:
        raise HTTPException(503, "Screenpipe bridge not available")
    if not _screenpipe.is_running():
        raise HTTPException(503, "Screenpipe not running. Start with: screenpipe")
    results = _screenpipe.search(q, content_type=content_type, limit=limit)
    return JSONResponse(content={"query": q, "count": len(results), "results": results})


@app.get("/screenpipe/context/recent")
def screenpipe_recent_context(minutes: int = Query(30, description="Lookback window in minutes")):
    """
    What has EVA seen and heard in the last N minutes?
    Powers real-time context injection into EVA's reasoning.
    """
    if not _screenpipe:
        raise HTTPException(503, "Screenpipe bridge not available")
    return JSONResponse(content=_screenpipe.get_recent_context(minutes=minutes))


@app.get("/screenpipe/context/today")
def screenpipe_today():
    """Full screen + audio summary for today from Screenpipe."""
    if not _screenpipe:
        raise HTTPException(503, "Screenpipe bridge not available")
    return JSONResponse(content=_screenpipe.get_today_summary())


@app.get("/screenpipe/transcript")
def screenpipe_transcript(
    start: str = Query(..., description="ISO datetime start (e.g. 2026-05-14T09:00)"),
    end: str = Query(..., description="ISO datetime end (e.g. 2026-05-14T10:00)"),
):
    """
    Extract a meeting transcript for a given time window.
    Returns full transcript text + timestamped segments.

    Example: /screenpipe/transcript?start=2026-05-14T09:00&end=2026-05-14T10:00
    """
    if not _screenpipe:
        raise HTTPException(503, "Screenpipe bridge not available")
    if not _screenpipe.is_running():
        raise HTTPException(503, "Screenpipe not running. Start with: screenpipe")
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Invalid datetime format. Use ISO 8601: 2026-05-14T09:00")
    transcript = _screenpipe.get_meeting_transcript(start_dt, end_dt)
    return JSONResponse(content=transcript)


@app.get("/context/unified")
def unified_context():
    """
    EVA's unified context — merges all available sources.
    Priority: Screenpipe (richest) → ActivityWatch → built-in logger.
    This is the primary endpoint EVA agents should query.
    """
    sources = {}

    # Screenpipe
    if _screenpipe and _screenpipe.is_running():
        sources["screenpipe"] = _screenpipe.get_today_summary()
        sources["screenpipe"]["recent_context"] = _screenpipe.get_recent_context(minutes=30)

    # ActivityWatch
    try:
        from eva_activitywatch_bridge import ActivityWatchBridge
        aw = ActivityWatchBridge()
        if aw.is_activitywatch_running():
            sources["activitywatch"] = aw.get_today_summary()
    except Exception:
        pass

    # Built-in logger (always available if running)
    today_events = load_events_for_date(date.today())
    if today_events:
        app_time = aggregate_app_time(today_events)
        total = sum(app_time.values())
        sources["eva_logger"] = {
            "event_count": len(today_events),
            "active_minutes": round(total / 60, 1),
            "top_apps": build_top_apps(app_time, total)[:5],
        }

    primary_source = (
        "screenpipe" if "screenpipe" in sources
        else "activitywatch" if "activitywatch" in sources
        else "eva_logger" if "eva_logger" in sources
        else None
    )

    return JSONResponse(content={
        "timestamp": datetime.now().isoformat()[:19],
        "primary_source": primary_source,
        "sources_available": list(sources.keys()),
        "data": sources,
        "eva_note": "Query /screenpipe/search?q=<topic> to search screen+audio memory.",
    })


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    log.info(f"Starting EVA Context API on port {API_PORT}")
    log.info(f"Data directory: {DATA_DIR}")
    log.info(f"Endpoints: /health /context/today /context/week /context/patterns /context/recent")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
