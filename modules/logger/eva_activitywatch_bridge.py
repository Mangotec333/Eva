#!/usr/bin/env python3
"""
eva_activitywatch_bridge.py — ActivityWatch ↔ EVA Bridge
Module 1 of EVA's architecture.

Provides a unified activity data interface that:
  1. Checks if ActivityWatch is running at http://localhost:5600
  2. If running  → fetches from ActivityWatch REST API and normalises to EVA
                   canonical format
  3. If not running → falls back to eva_logger.py JSONL data
  4. Exposes a single get_events() / get_today_summary() interface so that
     eva_context_api.py can call either source transparently.

Canonical EVA event format
--------------------------
{
    "eva_timestamp":  "2026-05-14T08:23:11",   # ISO-8601, second precision
    "source":         "activitywatch",           # or "eva_logger"
    "layer":          "behavior",
    "app":            "Cursor",
    "window":         "eva_logger.py — EVA Project",
    "category":       "deep_work",               # deep_work | browsing | communication | other
    "duration_seconds": 847,
    "session_id":     "uuid-or-aw-bucket-id",
    "goals_aligned":  null,                      # reserved for future goal-tracking module
    "eva_context": {
        "scheduled_priority": null,              # reserved for calendar integration
        "actual_activity":    "Cursor — coding",
        "alignment_score":    null               # reserved for alignment scoring
    }
}

Usage
-----
    from eva_activitywatch_bridge import ActivityWatchBridge

    bridge = ActivityWatchBridge()
    print(bridge.source)                    # "activitywatch" or "eva_logger"

    events  = bridge.get_events(date.today())       # list of canonical dicts
    summary = bridge.get_today_summary()            # aggregated summary dict

    # Check live status
    print(bridge.is_activitywatch_running())

Standalone test
---------------
    python eva_activitywatch_bridge.py
    python eva_activitywatch_bridge.py --date 2026-05-14
"""

import json
import logging
import sys
import uuid
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

AW_BASE_URL     = "http://localhost:5600/api/0"
AW_TIMEOUT      = 3          # seconds — fast timeout; AW responds instantly if running
DATA_DIR        = Path.home() / "eva-data"
ACTIVITY_DIR    = DATA_DIR / "activity"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVA-BRIDGE] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("eva_activitywatch_bridge")


# ─────────────────────────────────────────────
# Category mapping
# ─────────────────────────────────────────────

# Lowercase keyword → EVA category
# Checked against app name; first match wins.
CATEGORY_RULES: List[Tuple[str, str]] = [
    # deep_work — IDEs, editors, terminals, build tools
    ("cursor",      "deep_work"),
    ("vscode",      "deep_work"),
    ("code",        "deep_work"),     # catches "Visual Studio Code"
    ("xcode",       "deep_work"),
    ("pycharm",     "deep_work"),
    ("intellij",    "deep_work"),
    ("webstorm",    "deep_work"),
    ("clion",       "deep_work"),
    ("rubymine",    "deep_work"),
    ("goland",      "deep_work"),
    ("rider",       "deep_work"),
    ("android studio", "deep_work"),
    ("vim",         "deep_work"),
    ("neovim",      "deep_work"),
    ("nvim",        "deep_work"),
    ("emacs",       "deep_work"),
    ("sublime",     "deep_work"),
    ("terminal",    "deep_work"),
    ("iterm",       "deep_work"),
    ("alacritty",   "deep_work"),
    ("kitty",       "deep_work"),
    ("warp",        "deep_work"),
    ("hyper",       "deep_work"),
    ("bash",        "deep_work"),
    ("zsh",         "deep_work"),
    ("fish",        "deep_work"),
    ("powershell",  "deep_work"),
    ("cmd",         "deep_work"),
    ("python",      "deep_work"),
    ("node",        "deep_work"),
    ("jupyter",     "deep_work"),
    ("rstudio",     "deep_work"),
    ("matlab",      "deep_work"),

    # communication — chat, email, video calls, project management
    ("slack",       "communication"),
    ("discord",     "communication"),
    ("zoom",        "communication"),
    ("teams",       "communication"),
    ("meet",        "communication"),
    ("mail",        "communication"),    # Apple Mail, Outlook, Thunderbird
    ("outlook",     "communication"),
    ("gmail",       "communication"),
    ("telegram",    "communication"),
    ("whatsapp",    "communication"),
    ("messages",    "communication"),
    ("facetime",    "communication"),
    ("skype",       "communication"),
    ("notion",      "communication"),
    ("linear",      "communication"),
    ("jira",        "communication"),
    ("asana",       "communication"),
    ("trello",      "communication"),
    ("monday",      "communication"),

    # browsing — web browsers
    ("chrome",      "browsing"),
    ("chromium",    "browsing"),
    ("safari",      "browsing"),
    ("firefox",     "browsing"),
    ("edge",        "browsing"),
    ("brave",       "browsing"),
    ("arc",         "browsing"),
    ("opera",       "browsing"),
    ("vivaldi",     "browsing"),
    ("tor browser", "browsing"),
]


def categorize(app_name: str) -> str:
    """
    Return EVA category for an app name.
    Checks lowercase app name against CATEGORY_RULES; falls back to 'other'.
    """
    lower = app_name.lower()
    for keyword, category in CATEGORY_RULES:
        if keyword in lower:
            return category
    return "other"


def make_eva_event(
    timestamp: str,
    app: str,
    window: str,
    duration_seconds: float,
    source: str,
    session_id: str,
) -> dict:
    """Construct a canonical EVA event dict."""
    category = categorize(app)
    return {
        "eva_timestamp":    timestamp,
        "source":           source,
        "layer":            "behavior",
        "app":              app,
        "window":           window,
        "category":         category,
        "duration_seconds": round(duration_seconds, 1),
        "session_id":       session_id,
        "goals_aligned":    None,
        "eva_context": {
            "scheduled_priority": None,
            "actual_activity":    f"{app} — {category}",
            "alignment_score":    None,
        },
    }


# ─────────────────────────────────────────────
# ActivityWatch client
# ─────────────────────────────────────────────

class ActivityWatchClient:
    """
    Minimal HTTP client for the ActivityWatch REST API.
    Uses only stdlib urllib — no extra dependencies required.
    """

    def __init__(self, base_url: str = AW_BASE_URL, timeout: int = AW_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout

    def _get(self, path: str) -> Optional[dict]:
        """
        GET request to ActivityWatch API.
        Returns parsed JSON on success, None on any error.
        """
        url = f"{self.base_url}{path}"
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except (URLError, HTTPError, OSError) as e:
            log.debug(f"AW request failed ({url}): {e}")
            return None
        except json.JSONDecodeError as e:
            log.debug(f"AW JSON decode error ({url}): {e}")
            return None

    def is_running(self) -> bool:
        """Return True if ActivityWatch is reachable."""
        result = self._get("/buckets/")
        return result is not None

    def list_buckets(self) -> List[dict]:
        """Return list of all AW bucket descriptors. Returns [] on failure."""
        data = self._get("/buckets/")
        if data is None:
            return []
        # AW returns a dict of {bucket_id: bucket_info}
        if isinstance(data, dict):
            return list(data.values())
        return data  # future-proofing if AW ever returns a list

    def get_events(
        self,
        bucket_id: str,
        start: Optional[datetime] = None,
        end:   Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[dict]:
        """
        Fetch events from a single AW bucket.
        start/end are ISO-8601 strings sent as query params.
        Returns [] on failure.
        """
        params = [f"limit={limit}"]
        if start:
            params.append(f"start={_to_aw_ts(start)}")
        if end:
            params.append(f"end={_to_aw_ts(end)}")
        query_string = "&".join(params)
        path = f"/buckets/{bucket_id}/events?{query_string}"
        data = self._get(path)
        if data is None:
            return []
        return data if isinstance(data, list) else []


def _to_aw_ts(dt: datetime) -> str:
    """Format datetime as ActivityWatch expects: ISO-8601 with timezone."""
    if dt.tzinfo is None:
        # Assume local time; AW accepts naive ISO too but tz is safer
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


# ─────────────────────────────────────────────
# ActivityWatch normaliser
# ─────────────────────────────────────────────

# AW bucket types EVA cares about (by bucket type string from AW)
AW_WINDOW_TYPES    = {"currentwindow"}   # aw-watcher-window
AW_BROWSER_TYPES   = {"web.tab.current"} # aw-watcher-web (browser extension)
AW_AFK_TYPES       = {"afkstatus"}       # aw-watcher-afk

# AW event data keys for window buckets
AW_APP_KEYS    = ("app", "application", "process")
AW_TITLE_KEYS  = ("title", "window_title", "name")
AW_AFK_KEY     = "status"   # value is "not-afk" or "afk"


def _extract_aw_app_title(data: dict) -> Tuple[str, str]:
    """Pull app name and window title from an AW event's data payload."""
    app   = next((str(data[k]) for k in AW_APP_KEYS   if k in data), "unknown")
    title = next((str(data[k]) for k in AW_TITLE_KEYS if k in data), "")
    return app, title


def _parse_aw_timestamp(ts_str: str) -> Optional[datetime]:
    """
    Parse ActivityWatch timestamp.
    AW uses ISO-8601 with timezone, e.g. '2026-05-14T08:23:11.123456+00:00'.
    Returns naive local datetime.
    """
    try:
        # Python 3.7+ fromisoformat doesn't handle trailing 'Z'
        ts_str = ts_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(ts_str)
        # Convert to local time, strip tz info for consistency with eva_logger
        return dt_utc.astimezone(tz=None).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def normalise_aw_events(
    aw_events: List[dict],
    bucket_type: str,
    bucket_id: str,
) -> List[dict]:
    """
    Convert raw ActivityWatch events into canonical EVA events.
    Only processes window and browser bucket types; skips AFK and others.
    """
    if bucket_type not in AW_WINDOW_TYPES | AW_BROWSER_TYPES:
        return []

    canonical = []
    for ev in aw_events:
        # ── Parse timestamp ───────────────────────────────────
        ts_raw = ev.get("timestamp", "")
        dt = _parse_aw_timestamp(ts_raw)
        if dt is None:
            continue

        # ── Duration ──────────────────────────────────────────
        duration_secs = float(ev.get("duration", 0))
        if duration_secs <= 0:
            continue  # AW sometimes emits zero-duration heartbeats

        # ── App / window title ────────────────────────────────
        data = ev.get("data", {})
        app, window = _extract_aw_app_title(data)

        # Browser buckets: override app with browser app name if present,
        # use URL/title as window
        if bucket_type in AW_BROWSER_TYPES:
            url   = data.get("url", "")
            title = data.get("title", window)
            app   = data.get("app", app)   # browser name, e.g. "Chrome"
            window = f"{title} — {url}" if url else title

        canonical.append(
            make_eva_event(
                timestamp       = dt.isoformat(timespec="seconds"),
                app             = app,
                window          = window,
                duration_seconds= duration_secs,
                source          = "activitywatch",
                session_id      = bucket_id,  # use bucket as session proxy
            )
        )

    return canonical


# ─────────────────────────────────────────────
# eva_logger fallback reader
# ─────────────────────────────────────────────

def load_eva_logger_events(target_date: date) -> List[dict]:
    """
    Read JSONL from ~/eva-data/activity/YYYY-MM-DD.jsonl and
    convert window_focus events to canonical EVA format.
    Silently returns [] if file doesn't exist or is unreadable.
    """
    path = ACTIVITY_DIR / f"{target_date.isoformat()}.jsonl"
    if not path.exists():
        return []

    canonical = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only convert window_focus events — they carry duration data
            if ev.get("event_type") != "window_focus":
                continue

            canonical.append(
                make_eva_event(
                    timestamp        = ev.get("timestamp", ""),
                    app              = ev.get("app_name", "unknown"),
                    window           = ev.get("window_title", ""),
                    duration_seconds = ev.get("duration_seconds", 0),
                    source           = "eva_logger",
                    session_id       = ev.get("session_id", str(uuid.uuid4())),
                )
            )
    return canonical


# ─────────────────────────────────────────────
# Unified summary builder
# ─────────────────────────────────────────────

def build_summary_from_events(events: List[dict], target_date: date) -> dict:
    """
    Aggregate a list of canonical EVA events into a daily summary dict.
    Compatible with the shape eva_context_api.py expects.
    """
    if not events:
        return {
            "date":                     target_date.isoformat(),
            "source":                   "none",
            "total_active_minutes":     0,
            "category_breakdown":       {c: 0 for c in ("deep_work", "browsing", "communication", "other")},
            "top_apps":                 [],
            "context_switches":         len(events),
            "peak_focus_hour":          "unknown",
            "longest_focus_block":      {"app": "none", "minutes": 0},
        }

    # Time per app and per category
    app_secs:  Dict[str, float] = defaultdict(float)
    cat_secs:  Dict[str, float] = defaultdict(float)
    hour_secs: Dict[int,  float] = defaultdict(float)

    longest_ev = None

    for ev in events:
        dur  = ev.get("duration_seconds", 0)
        app  = ev.get("app", "unknown")
        cat  = ev.get("category", "other")
        app_secs[app] += dur
        cat_secs[cat] += dur

        try:
            hr = datetime.fromisoformat(ev["eva_timestamp"]).hour
            hour_secs[hr] += dur
        except (KeyError, ValueError):
            pass

        if longest_ev is None or dur > longest_ev.get("duration_seconds", 0):
            longest_ev = ev

    total_secs = sum(app_secs.values())

    top_apps = [
        {
            "app":        app,
            "minutes":    round(secs / 60, 1),
            "percentage": round((secs / total_secs) * 100, 1) if total_secs > 0 else 0,
        }
        for app, secs in sorted(app_secs.items(), key=lambda x: -x[1])
    ]

    peak_hour = (
        f"{max(hour_secs, key=hour_secs.get):02d}:00"
        if hour_secs else "unknown"
    )

    source_vals = {ev.get("source", "unknown") for ev in events}
    source_str  = "+".join(sorted(source_vals))

    return {
        "date":                 target_date.isoformat(),
        "source":               source_str,
        "total_active_minutes": round(total_secs / 60, 1),
        "category_breakdown": {
            "deep_work":     round(cat_secs.get("deep_work",     0) / 60, 1),
            "browsing":      round(cat_secs.get("browsing",      0) / 60, 1),
            "communication": round(cat_secs.get("communication", 0) / 60, 1),
            "other":         round(cat_secs.get("other",         0) / 60, 1),
        },
        "top_apps":     top_apps[:10],
        "context_switches": len(events),
        "peak_focus_hour":  peak_hour,
        "longest_focus_block": {
            "app":     longest_ev.get("app", "none") if longest_ev else "none",
            "minutes": round(longest_ev.get("duration_seconds", 0) / 60, 1) if longest_ev else 0,
        },
    }


# ─────────────────────────────────────────────
# Public bridge interface
# ─────────────────────────────────────────────

class ActivityWatchBridge:
    """
    Single entry point for all activity data.

    EVA modules should import and use this class; they don't need to know
    whether data is coming from ActivityWatch or eva_logger.

    Example
    -------
        bridge = ActivityWatchBridge()
        events  = bridge.get_events(date.today())
        summary = bridge.get_today_summary()
        print(bridge.source)   # "activitywatch" or "eva_logger"
    """

    def __init__(self, aw_base_url: str = AW_BASE_URL):
        self._aw = ActivityWatchClient(base_url=aw_base_url)
        self._aw_available: Optional[bool] = None  # cached after first check

    # ── Source detection ────────────────────────────────────────────────

    def is_activitywatch_running(self) -> bool:
        """Check (and cache) whether ActivityWatch is reachable."""
        if self._aw_available is None:
            self._aw_available = self._aw.is_running()
            log.info(
                f"ActivityWatch {'detected' if self._aw_available else 'not detected'} "
                f"at {self._aw.base_url}"
            )
        return self._aw_available

    @property
    def source(self) -> str:
        """Return 'activitywatch' or 'eva_logger' based on availability."""
        return "activitywatch" if self.is_activitywatch_running() else "eva_logger"

    # ── Data retrieval ──────────────────────────────────────────────────

    def get_events(
        self,
        target_date: date,
        force_source: Optional[str] = None,
    ) -> List[dict]:
        """
        Return canonical EVA events for the given date.

        Args:
            target_date:  The date to fetch events for.
            force_source: 'activitywatch' or 'eva_logger' to override auto-detect.

        Returns:
            List of canonical EVA event dicts, sorted by eva_timestamp ascending.
        """
        use_aw = (
            self.is_activitywatch_running()
            if force_source is None
            else (force_source == "activitywatch")
        )

        if use_aw:
            events = self._fetch_from_activitywatch(target_date)
            if events:
                log.info(f"Loaded {len(events)} events from ActivityWatch for {target_date}")
                return events
            # AW returned nothing (e.g. no data for this date) — try fallback
            log.warning("ActivityWatch returned no events — falling back to eva_logger data")

        events = load_eva_logger_events(target_date)
        log.info(f"Loaded {len(events)} events from eva_logger for {target_date}")
        return events

    def get_today_summary(self, force_source: Optional[str] = None) -> dict:
        """Return aggregated summary for today."""
        today  = date.today()
        events = self.get_events(today, force_source=force_source)
        return build_summary_from_events(events, today)

    def get_date_summary(self, target_date: date, force_source: Optional[str] = None) -> dict:
        """Return aggregated summary for an arbitrary date."""
        events = self.get_events(target_date, force_source=force_source)
        return build_summary_from_events(events, target_date)

    # ── ActivityWatch fetch internals ────────────────────────────────────

    def _fetch_from_activitywatch(self, target_date: date) -> List[dict]:
        """
        Pull and normalise all relevant AW buckets for a given date.
        Merges window-watcher and browser-watcher events into one stream.
        """
        # Build time window in local time
        start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end_dt   = start_dt + timedelta(days=1)

        buckets = self._aw.list_buckets()
        if not buckets:
            log.warning("ActivityWatch returned no buckets")
            return []

        all_events: List[dict] = []

        for bucket in buckets:
            bucket_id   = bucket.get("id",   "")
            bucket_type = bucket.get("type",  "")

            # Only process window and browser buckets
            if bucket_type not in AW_WINDOW_TYPES | AW_BROWSER_TYPES:
                log.debug(f"Skipping bucket '{bucket_id}' (type: '{bucket_type}')")
                continue

            raw_events = self._aw.get_events(
                bucket_id,
                start = start_dt,
                end   = end_dt,
            )
            log.debug(f"Bucket '{bucket_id}' ({bucket_type}): {len(raw_events)} raw events")

            canonical = normalise_aw_events(raw_events, bucket_type, bucket_id)
            all_events.extend(canonical)

        # Sort by timestamp ascending
        all_events.sort(key=lambda e: e.get("eva_timestamp", ""))
        return all_events

    # ── Status report ────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a human-readable status dict (used by /health endpoints)."""
        aw_running = self.is_activitywatch_running()
        buckets    = self._aw.list_buckets() if aw_running else []
        bucket_ids = [b.get("id", "") for b in buckets]

        today_events = self.get_events(date.today())
        summary      = build_summary_from_events(today_events, date.today())

        return {
            "active_source":         self.source,
            "activitywatch_running": aw_running,
            "activitywatch_url":     self._aw.base_url,
            "aw_buckets":            bucket_ids,
            "eva_logger_data_dir":   str(ACTIVITY_DIR),
            "eva_logger_files":      sorted(
                str(p.name) for p in ACTIVITY_DIR.glob("*.jsonl")
            ) if ACTIVITY_DIR.exists() else [],
            "today_events_count":    len(today_events),
            "today_active_minutes":  summary.get("total_active_minutes", 0),
            "today_source":          summary.get("source", "none"),
        }


# ─────────────────────────────────────────────
# Standalone test / CLI
# ─────────────────────────────────────────────

def _print_event_table(events: List[dict], max_rows: int = 20):
    if not events:
        print("  (no events)")
        return
    shown = events[:max_rows]
    print(f"  {'Timestamp':20s}  {'Source':14s}  {'Category':14s}  {'App':22s}  {'Dur(s)':>7s}")
    print(f"  {'─'*20}  {'─'*14}  {'─'*14}  {'─'*22}  {'─'*7}")
    for ev in shown:
        ts  = ev.get("eva_timestamp", "")[-8:]  # HH:MM:SS
        src = ev.get("source",   "")[:14]
        cat = ev.get("category", "")[:14]
        app = ev.get("app",      "")[:22]
        dur = ev.get("duration_seconds", 0)
        print(f"  {ts:20s}  {src:14s}  {cat:14s}  {app:22s}  {dur:7.1f}")
    if len(events) > max_rows:
        print(f"  ... and {len(events) - max_rows} more events")


def main():
    parser = argparse.ArgumentParser(
        description="EVA ActivityWatch Bridge — standalone status check"
    )
    parser.add_argument(
        "--date",
        help="Date to inspect (YYYY-MM-DD). Defaults to today.",
        default=None,
    )
    parser.add_argument(
        "--source",
        choices=["activitywatch", "eva_logger"],
        help="Force a specific data source (overrides auto-detect).",
        default=None,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output summary as JSON (machine-readable).",
    )
    args = parser.parse_args()

    target_date = date.today()
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: Invalid date '{args.date}'. Use YYYY-MM-DD.")
            sys.exit(1)

    bridge  = ActivityWatchBridge()
    status  = bridge.status()
    events  = bridge.get_events(target_date, force_source=args.source)
    summary = build_summary_from_events(events, target_date)

    if args.output_json:
        print(json.dumps({"status": status, "summary": summary}, indent=2))
        return

    # ── Human-readable report ─────────────────────────────────────────
    width = 62
    sep   = "═" * width
    thin  = "─" * width

    print(f"\n{sep}")
    print(f"  EVA ACTIVITYWATCH BRIDGE — {target_date.isoformat()}")
    print(sep)

    # Source status
    aw_icon = "✓" if status["activitywatch_running"] else "✗"
    print(f"\n  ActivityWatch running   : {aw_icon}  ({status['activitywatch_url']})")
    print(f"  Active data source      : {status['active_source'].upper()}")
    if status["aw_buckets"]:
        print(f"  AW buckets found        : {len(status['aw_buckets'])}")
        for b in status["aw_buckets"]:
            print(f"    • {b}")
    print(f"  eva_logger files        : {len(status['eva_logger_files'])} day(s) on disk")
    print(f"  Today's events          : {status['today_events_count']}")
    print(f"  Today's active minutes  : {status['today_active_minutes']}")

    print(f"\n{thin}")
    print(f"  CATEGORY BREAKDOWN  (source: {summary['source']})")
    print(thin)
    cat_bd = summary.get("category_breakdown", {})
    total_min = summary["total_active_minutes"]
    for cat, mins in cat_bd.items():
        bar_len = int((mins / max(total_min, 1)) * 28)
        bar = "█" * bar_len
        print(f"  {cat:15s}  {mins:6.1f} min  {bar}")

    print(f"\n{thin}")
    print("  TOP APPS")
    print(thin)
    _print_event_table(events)

    print(f"\n{thin}")
    print("  SUMMARY")
    print(thin)
    print(f"  Total active    : {total_min} min")
    print(f"  Peak hour       : {summary['peak_focus_hour']}")
    lf = summary.get("longest_focus_block", {})
    print(f"  Longest block   : {lf.get('minutes', 0)} min  [{lf.get('app', 'none')}]")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
