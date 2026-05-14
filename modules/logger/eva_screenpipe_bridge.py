#!/usr/bin/env python3
"""
eva_screenpipe_bridge.py — Screenpipe ↔ EVA Bridge
Module 1b of EVA's sensing architecture.

Screenpipe runs locally at http://localhost:3030 and provides:
  - OCR text extracted from every screen frame (what you READ)
  - Audio transcriptions from mic + system audio (what you SAID and HEARD)
  - Frame metadata (timestamps, app names, window titles)
  - Full-text search across everything ever seen or heard

This bridge:
  1. Checks if Screenpipe is running at localhost:3030
  2. Normalizes Screenpipe data into EVA's canonical format
  3. Provides semantic search across screen + audio history
  4. Exposes meeting detection and transcript extraction
  5. Falls back gracefully if Screenpipe is not running

Screenpipe REST API (localhost:3030):
  GET /search?q=<query>&content_type=ocr|audio|all&limit=<n>
  GET /frames?start=<iso>&end=<iso>
  GET /audio/list?start=<iso>&end=<iso>
  GET /health
  GET /pipes/list

EVA Canonical format (screen layer):
{
    "eva_timestamp":  "2026-05-14T08:23:11",
    "source":         "screenpipe",
    "layer":          "screen|audio",
    "app":            "Cursor",
    "window":         "eva_logger.py — EVA Project",
    "category":       "deep_work",
    "duration_seconds": 30,
    "session_id":     "frame-uuid",
    "content": {
        "type":       "ocr|audio",
        "text":       "extracted text or transcript",
        "confidence": 0.95
    },
    "goals_aligned":  null,
    "eva_context": {
        "scheduled_priority": null,
        "actual_activity":    "Reading — EVA architecture docs",
        "alignment_score":    null
    }
}

Usage:
    from eva_screenpipe_bridge import ScreenpipeBridge

    sp = ScreenpipeBridge()
    print(sp.is_running())                              # True/False
    print(sp.get_today_summary())                       # aggregated dict
    results = sp.search("RCFE investor", content_type="all")
    transcript = sp.get_meeting_transcript(start, end)
    events = sp.get_events_for_date(date.today())
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime, timedelta
from typing import Optional
import uuid
import sys

# ─── Constants ────────────────────────────────────────────────────────────────

SCREENPIPE_BASE = "http://localhost:3030"
TIMEOUT_SECONDS = 3

# Category mapping from app name → EVA category
CATEGORY_RULES = {
    "deep_work": [
        "cursor", "vs code", "vscode", "xcode", "pycharm", "intellij",
        "terminal", "iterm", "iterm2", "warp", "hyper", "zed",
        "vim", "neovim", "emacs", "sublime", "atom", "notepad++",
        "android studio", "webstorm", "goland", "clion", "rider",
        "jupyter", "rstudio", "matlab", "spyder",
    ],
    "communication": [
        "slack", "discord", "teams", "zoom", "google meet", "webex",
        "gmail", "mail", "outlook", "apple mail", "thunderbird",
        "messages", "imessage", "whatsapp", "telegram", "signal",
        "notion", "linear", "jira", "asana", "monday", "clickup",
        "loom", "around", "gather",
    ],
    "browsing": [
        "chrome", "safari", "firefox", "arc", "edge", "brave",
        "opera", "vivaldi", "tor browser",
    ],
    "media": [
        "youtube", "netflix", "spotify", "apple music", "vlc",
        "quicktime", "plex", "twitch", "hbo", "disney+",
    ],
}

def _categorize(app_name: str, window_title: str = "") -> str:
    """Map app name to EVA category."""
    combined = f"{app_name} {window_title}".lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(k in combined for k in keywords):
            return category
    return "other"


# ─── HTTP Client ──────────────────────────────────────────────────────────────

class _ScreenpipeHTTP:
    """Minimal stdlib HTTP client for Screenpipe API."""

    def __init__(self, base_url: str = SCREENPIPE_BASE, timeout: int = TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            return None
        except json.JSONDecodeError:
            return None
        except Exception:
            return None


# ─── Screenpipe Bridge ────────────────────────────────────────────────────────

class ScreenpipeBridge:
    """
    EVA's interface to Screenpipe.
    Provides screen memory, OCR search, and audio transcript access.
    """

    def __init__(self):
        self._http = _ScreenpipeHTTP()
        self._running: Optional[bool] = None

    # ── Status ────────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Check if Screenpipe is running. Cached per instance."""
        if self._running is None:
            result = self._http.get("/health")
            self._running = result is not None
        return self._running

    def status(self) -> dict:
        """Full diagnostic snapshot."""
        if not self.is_running():
            return {
                "running": False,
                "source": "screenpipe",
                "message": "Screenpipe not running. Install: brew install screenpipe",
                "install_url": "https://github.com/screenpipe/screenpipe/releases",
            }
        health = self._http.get("/health") or {}
        return {
            "running": True,
            "source": "screenpipe",
            "version": health.get("version", "unknown"),
            "uptime_seconds": health.get("uptime_seconds"),
            "message": "Screenpipe running — EVA screen memory active",
        }

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        content_type: str = "all",
        limit: int = 20,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Semantic search across screen + audio history.

        content_type: "ocr" | "audio" | "all"

        Returns list of EVA canonical events with content field.
        """
        if not self.is_running():
            return []

        params = {
            "q": query,
            "content_type": content_type,
            "limit": limit,
        }
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()

        result = self._http.get("/search", params=params)
        if not result:
            return []

        items = result.get("data", result.get("results", []))
        return [self._normalize_search_result(item) for item in items]

    # ── Events for a date ─────────────────────────────────────────────────────

    def get_events_for_date(self, target_date: date) -> list[dict]:
        """
        Get all screen events for a given date.
        Returns EVA canonical events (screen layer).
        """
        if not self.is_running():
            return []

        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)

        result = self._http.get("/frames", params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 1000,
        })
        if not result:
            return []

        frames = result.get("data", result.get("frames", []))
        return [self._normalize_frame(f) for f in frames if f]

    # ── Audio / Meeting Transcripts ───────────────────────────────────────────

    def get_audio_for_period(
        self,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get audio transcriptions for a time period.
        Useful for meeting transcript extraction.
        """
        if not self.is_running():
            return []

        result = self._http.get("/search", params={
            "q": "",
            "content_type": "audio",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "limit": limit,
        })
        if not result:
            return []

        items = result.get("data", result.get("results", []))
        return [self._normalize_search_result(item) for item in items]

    def get_meeting_transcript(
        self,
        start: datetime,
        end: datetime,
    ) -> dict:
        """
        Extract a meeting transcript for a given time window.
        Returns structured transcript with speaker segments.
        """
        audio_events = self.get_audio_for_period(start, end)
        if not audio_events:
            return {
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "transcript": "",
                "segments": [],
                "duration_minutes": int((end - start).total_seconds() / 60),
                "word_count": 0,
            }

        segments = []
        full_text = []
        for evt in audio_events:
            text = evt.get("content", {}).get("text", "")
            if text.strip():
                segments.append({
                    "timestamp": evt["eva_timestamp"],
                    "text": text.strip(),
                    "source": evt.get("layer", "audio"),
                })
                full_text.append(text.strip())

        transcript = " ".join(full_text)
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "transcript": transcript,
            "segments": segments,
            "duration_minutes": int((end - start).total_seconds() / 60),
            "word_count": len(transcript.split()),
        }

    # ── Daily Summary ─────────────────────────────────────────────────────────

    def get_today_summary(self) -> dict:
        """
        Aggregate today's screen + audio into an EVA daily summary.
        Mirrors the format of ActivityWatchBridge.get_today_summary().
        """
        if not self.is_running():
            return self._empty_summary()

        today = date.today()
        events = self.get_events_for_date(today)

        if not events:
            return self._empty_summary()

        # Aggregate by app
        app_durations: dict[str, float] = {}
        categories: dict[str, float] = {}
        ocr_texts: list[str] = []

        for evt in events:
            app = evt.get("app", "unknown")
            dur = evt.get("duration_seconds", 30)  # default frame interval
            cat = evt.get("category", "other")

            app_durations[app] = app_durations.get(app, 0) + dur
            categories[cat] = categories.get(cat, 0) + dur

            content = evt.get("content", {})
            if content.get("type") == "ocr" and content.get("text"):
                ocr_texts.append(content["text"])

        total_seconds = sum(app_durations.values())
        top_apps = sorted(
            [{"app": k, "minutes": round(v / 60, 1), "percentage": round(v / total_seconds * 100) if total_seconds else 0}
             for k, v in app_durations.items()],
            key=lambda x: x["minutes"],
            reverse=True,
        )[:10]

        return {
            "date": today.isoformat(),
            "source": "screenpipe",
            "total_active_minutes": round(total_seconds / 60, 1),
            "top_apps": top_apps,
            "categories": {k: round(v / 60, 1) for k, v in categories.items()},
            "ocr_text_count": len(ocr_texts),
            "has_audio": any(e.get("layer") == "audio" for e in events),
            "event_count": len(events),
        }

    # ── OCR Context ───────────────────────────────────────────────────────────

    def get_recent_context(self, minutes: int = 30) -> dict:
        """
        What has the user been looking at / hearing in the last N minutes?
        Powers EVA's real-time context awareness.
        """
        if not self.is_running():
            return {"running": False, "context": "", "events": []}

        end = datetime.now()
        start = end - timedelta(minutes=minutes)

        # Search recent screen content
        screen_events = self.get_events_for_date(date.today())
        recent = [
            e for e in screen_events
            if e.get("eva_timestamp", "") >= start.isoformat()
        ]

        # Extract readable context
        texts = [
            e["content"]["text"]
            for e in recent
            if e.get("content", {}).get("text")
        ]
        context_summary = " | ".join(texts[-10:]) if texts else ""

        return {
            "running": True,
            "period_minutes": minutes,
            "event_count": len(recent),
            "context": context_summary[:1000],  # cap at 1000 chars for LLM context
            "events": recent[:20],
        }

    # ── Normalization ─────────────────────────────────────────────────────────

    def _normalize_frame(self, frame: dict) -> dict:
        """Normalize a Screenpipe frame into EVA canonical format."""
        app = frame.get("app_name", frame.get("app", "unknown"))
        window = frame.get("window_name", frame.get("window", ""))
        timestamp = frame.get("timestamp", frame.get("created_at", datetime.now().isoformat()))

        # Normalize timestamp
        if isinstance(timestamp, str) and "T" in timestamp:
            ts = timestamp[:19]
        else:
            ts = datetime.now().isoformat()[:19]

        content_data = frame.get("content", {})
        ocr_text = (
            content_data.get("text", "")
            if isinstance(content_data, dict)
            else str(content_data)
        )

        return {
            "eva_timestamp": ts,
            "source": "screenpipe",
            "layer": "screen",
            "app": app,
            "window": window,
            "category": _categorize(app, window),
            "duration_seconds": 30,  # Screenpipe default frame interval
            "session_id": frame.get("id", str(uuid.uuid4())),
            "content": {
                "type": "ocr",
                "text": ocr_text,
                "confidence": frame.get("confidence", None),
            },
            "goals_aligned": None,
            "eva_context": {
                "scheduled_priority": None,
                "actual_activity": f"{app} — {window[:60]}" if window else app,
                "alignment_score": None,
            },
        }

    def _normalize_search_result(self, item: dict) -> dict:
        """Normalize a Screenpipe search result into EVA canonical format."""
        content_type = item.get("type", "ocr")
        content = item.get("content", {})

        if isinstance(content, str):
            text = content
            app = "unknown"
            window = ""
            timestamp = datetime.now().isoformat()[:19]
        else:
            text = content.get("text", content.get("transcription", ""))
            app = content.get("app_name", content.get("app", "unknown"))
            window = content.get("window_name", content.get("window", ""))
            timestamp = (
                content.get("timestamp", item.get("timestamp", datetime.now().isoformat()))
            )
            if isinstance(timestamp, str):
                timestamp = timestamp[:19]

        return {
            "eva_timestamp": timestamp,
            "source": "screenpipe",
            "layer": content_type,
            "app": app,
            "window": window,
            "category": _categorize(app, window),
            "duration_seconds": content.get("duration", 30),
            "session_id": item.get("id", str(uuid.uuid4())),
            "content": {
                "type": content_type,
                "text": text,
                "confidence": content.get("confidence", None),
            },
            "goals_aligned": None,
            "eva_context": {
                "scheduled_priority": None,
                "actual_activity": f"{'Reading' if content_type == 'ocr' else 'Speaking/Listening'} — {app}",
                "alignment_score": None,
            },
        }

    def _empty_summary(self) -> dict:
        return {
            "date": date.today().isoformat(),
            "source": "screenpipe",
            "running": False,
            "total_active_minutes": 0,
            "top_apps": [],
            "categories": {},
            "ocr_text_count": 0,
            "has_audio": False,
            "event_count": 0,
            "message": "Screenpipe not running. Start with: screenpipe",
        }


# ─── CLI Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("EVA Screenpipe Bridge — Diagnostic")
    print("=" * 50)

    bridge = ScreenpipeBridge()
    status = bridge.status()

    print(f"Status: {'✅ RUNNING' if status['running'] else '❌ NOT RUNNING'}")
    print(f"Message: {status['message']}")

    if status["running"]:
        print("\n--- Today's Summary ---")
        summary = bridge.get_today_summary()
        print(f"Total active: {summary['total_active_minutes']} minutes")
        print(f"Events captured: {summary['event_count']}")
        print(f"OCR text blocks: {summary['ocr_text_count']}")
        print(f"Audio captured: {summary['has_audio']}")

        if summary["top_apps"]:
            print("\nTop apps:")
            for app in summary["top_apps"][:5]:
                print(f"  {app['app']}: {app['minutes']} min ({app['percentage']}%)")

        print("\n--- Recent Context (last 15 min) ---")
        ctx = bridge.get_recent_context(minutes=15)
        print(f"Events: {ctx['event_count']}")
        if ctx["context"]:
            print(f"Context preview: {ctx['context'][:200]}...")

        if "--search" in sys.argv:
            idx = sys.argv.index("--search")
            query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "EVA"
            print(f"\n--- Search: '{query}' ---")
            results = bridge.search(query, limit=5)
            for r in results:
                print(f"  [{r['layer']}] {r['app']}: {r['content']['text'][:100]}")
    else:
        print("\n📦 To install Screenpipe:")
        print("  macOS:   brew install screenpipe")
        print("  Windows: https://github.com/screenpipe/screenpipe/releases")
        print("  Linux:   https://github.com/screenpipe/screenpipe/releases")
        print("\n▶  To start: screenpipe")
        print("   Then re-run this script to verify.")
