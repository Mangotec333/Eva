#!/usr/bin/env python3
"""
EVA Screenpipe Watchdog
Starts/pauses Screenpipe based on:
1. Active macOS application (work vs pause vs research)
2. HID idle time (keyboard/mouse inactivity)
3. Work session context for RESEARCH_APPS (YouTube etc.)

Runs as a launchd agent. Polls every 30 seconds.
Logs to ~/Eva/logs/screenpipe-watchdog.log
"""

import subprocess
import time
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

POLL_INTERVAL = 30          # seconds between checks
IDLE_THRESHOLD = 600        # 10 min idle → pause Screenpipe
WORK_SESSION_WINDOW = 1800  # 30 min since last work app → research mode off
LOG_PATH = Path.home() / "Eva" / "logs" / "screenpipe-watchdog.log"

# Screenpipe always runs when these apps are active
WORK_APPS = {
    "Cursor", "Code", "Visual Studio Code",
    "Terminal", "iTerm2", "iTerm",
    "Google Chrome", "Safari", "Firefox", "Arc",
    "Notion", "Obsidian", "Notes",
    "Slack", "Mail", "Zoom", "Microsoft Teams",
    "Perplexity", "Perplexity Computer", "Claude",
    "Xcode", "PyCharm", "WebStorm",
    "Finder",  # file management counts
}

# Only runs if a WORK_APP was active in the last 30 min
RESEARCH_APPS = {
    "YouTube",      # keynote research, EVA build reference
    "Google Chrome",  # already in WORK_APPS but YouTube detection is URL-based
}

# Screenpipe always pauses when these apps are active
PAUSE_APPS = {
    "Netflix", "Spotify", "VLC", "QuickTime Player",
    "App Store", "System Preferences", "System Settings",
    "Photos", "FaceTime", "Music", "Podcasts",
    "TV", "Apple TV",
}

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────────────────────────

screenpipe_running = False
last_work_app_time: float = 0.0

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_active_app() -> str:
    """Get the frontmost application name via AppleScript."""
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""

def get_hid_idle_seconds() -> float:
    """Get seconds since last keyboard/mouse activity using ioreg."""
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "HIDIdleTime" in line:
                ns = int(line.split("=")[-1].strip())
                return ns / 1_000_000_000  # nanoseconds → seconds
    except Exception:
        pass
    return 0.0

def is_screenpipe_running() -> bool:
    """Check if screenpipe process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "screenpipe"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def start_screenpipe():
    """Start Screenpipe in background."""
    global screenpipe_running
    if not is_screenpipe_running():
        try:
            subprocess.Popen(
                ["screenpipe"],
                stdout=open(Path.home() / "Eva" / "logs" / "screenpipe.log", "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            screenpipe_running = True
            log.info("Screenpipe STARTED")
        except FileNotFoundError:
            log.warning("screenpipe not found — install with: brew install screenpipe")
        except Exception as e:
            log.error(f"Failed to start Screenpipe: {e}")
    else:
        screenpipe_running = True

def pause_screenpipe():
    """Stop Screenpipe gracefully."""
    global screenpipe_running
    if is_screenpipe_running():
        try:
            subprocess.run(["pkill", "-x", "screenpipe"], timeout=5)
            screenpipe_running = False
            log.info("Screenpipe PAUSED")
        except Exception as e:
            log.error(f"Failed to pause Screenpipe: {e}")
    else:
        screenpipe_running = False

def should_run_screenpipe(active_app: str, idle_seconds: float) -> tuple[bool, str]:
    """
    Returns (should_run: bool, reason: str)

    Logic:
    1. If idle > threshold → pause
    2. If active app is in PAUSE_APPS → pause
    3. If active app is in WORK_APPS → run
    4. If active app is in RESEARCH_APPS AND work session active → run
    5. Otherwise → maintain current state
    """
    global last_work_app_time

    # Rule 1: idle too long
    if idle_seconds > IDLE_THRESHOLD:
        return False, f"idle {idle_seconds/60:.1f}min > threshold"

    # Rule 2: explicit pause app
    if active_app in PAUSE_APPS:
        return False, f"pause app: {active_app}"

    # Rule 3: work app — always run, update last work time
    if active_app in WORK_APPS:
        last_work_app_time = time.time()
        return True, f"work app: {active_app}"

    # Rule 4: research app — only if work session active
    if active_app in RESEARCH_APPS:
        work_session_age = time.time() - last_work_app_time
        if last_work_app_time > 0 and work_session_age < WORK_SESSION_WINDOW:
            return True, f"research app in active session ({work_session_age/60:.0f}min since work)"
        else:
            return False, f"research app but no active work session"

    # Rule 5: unknown app — maintain current state
    return screenpipe_running, f"unknown app '{active_app}' — maintaining state"

# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    log.info("EVA Screenpipe Watchdog started")
    log.info(f"Poll interval: {POLL_INTERVAL}s | Idle threshold: {IDLE_THRESHOLD/60:.0f}min | Work session window: {WORK_SESSION_WINDOW/60:.0f}min")

    while True:
        try:
            active_app = get_active_app()
            idle_secs = get_hid_idle_seconds()
            should_run, reason = should_run_screenpipe(active_app, idle_secs)

            currently_running = is_screenpipe_running()

            if should_run and not currently_running:
                log.info(f"Starting — {reason}")
                start_screenpipe()
            elif not should_run and currently_running:
                log.info(f"Pausing — {reason}")
                pause_screenpipe()
            # else: no change needed

        except Exception as e:
            log.error(f"Watchdog loop error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
