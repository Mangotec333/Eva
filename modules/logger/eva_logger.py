#!/usr/bin/env python3
"""
eva_logger.py — EVA Activity Logger Daemon
Module 1 of EVA's architecture.

Tracks active window, application usage, idle time, and work sessions.
Logs every event as JSON Lines to ~/eva-data/activity/YYYY-MM-DD.jsonl.

Usage:
    python eva_logger.py            # Run as background daemon
    python eva_logger.py --test     # Run for 60 seconds, print captured data
"""

import os
import sys
import json
import time
import uuid
import signal
import logging
import platform
import threading
import subprocess
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

POLL_INTERVAL = 10          # seconds between window polls
IDLE_THRESHOLD = 300        # seconds of no input before marking idle (5 min)
DATA_DIR = Path.home() / "eva-data"
ACTIVITY_DIR = DATA_DIR / "activity"
SUMMARIES_DIR = DATA_DIR / "summaries"
LOG_LEVEL = logging.INFO

# ─────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [EVA-LOGGER] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("eva_logger")


# ─────────────────────────────────────────────
# Platform-specific window detection
# ─────────────────────────────────────────────

class WindowDetector:
    """
    Detects the currently focused window and application.
    Provides graceful fallbacks for each platform.
    """

    def __init__(self):
        self.platform = platform.system()
        self._available = self._check_availability()
        log.info(f"Platform: {self.platform} | Tracker available: {self._available}")

    def _check_availability(self) -> bool:
        """Check whether the platform tool is available."""
        try:
            if self.platform == "Darwin":
                # macOS: osascript is always available
                return True
            elif self.platform == "Windows":
                try:
                    import win32gui  # pywin32
                    return True
                except ImportError:
                    # Fallback: PowerShell
                    result = subprocess.run(
                        ["powershell", "-Command", "echo test"],
                        capture_output=True, timeout=3
                    )
                    return result.returncode == 0
            elif self.platform == "Linux":
                result = subprocess.run(
                    ["which", "xdotool"], capture_output=True, timeout=3
                )
                return result.returncode == 0
        except Exception as e:
            log.warning(f"Availability check failed: {e}")
        return False

    def get_active_window(self) -> dict:
        """
        Returns dict with 'app_name' and 'window_title'.
        Falls back to {"app_name": "unknown", "window_title": "unknown"} on failure.
        """
        try:
            if self.platform == "Darwin":
                return self._get_macos_window()
            elif self.platform == "Windows":
                return self._get_windows_window()
            elif self.platform == "Linux":
                return self._get_linux_window()
        except Exception as e:
            log.debug(f"Window detection error: {e}")
        return {"app_name": "unknown", "window_title": "unknown"}

    def _get_macos_window(self) -> dict:
        """Use osascript to get frontmost app and window title on macOS."""
        script = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
end tell
set appName to frontApp
set windowTitle to ""
try
    tell application frontApp
        set windowTitle to name of front window
    end tell
end try
return appName & "|" & windowTitle
'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|", 1)
            app_name = parts[0].strip() if parts else "unknown"
            window_title = parts[1].strip() if len(parts) > 1 else ""
            return {"app_name": app_name, "window_title": window_title}
        raise RuntimeError(result.stderr.strip())

    def _get_windows_window(self) -> dict:
        """Use pywin32 or PowerShell to get active window on Windows."""
        try:
            import win32gui
            import win32process
            import psutil
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            app_name = proc.name().replace(".exe", "")
            return {"app_name": app_name, "window_title": window_title}
        except ImportError:
            pass

        # PowerShell fallback
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$h = [System.Windows.Forms.Form]::ActiveForm; "
            "if ($h) { $h.Text } else { "
            "  $proc = Get-Process | Where-Object {$_.MainWindowHandle -ne 0} | "
            "  Sort-Object CPU -Descending | Select-Object -First 1; "
            "  Write-Output ($proc.ProcessName + '|' + $proc.MainWindowTitle) }"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|", 1)
            app_name = parts[0].strip() if parts else "unknown"
            window_title = parts[1].strip() if len(parts) > 1 else ""
            return {"app_name": app_name, "window_title": window_title}
        raise RuntimeError(result.stderr.strip())

    def _get_linux_window(self) -> dict:
        """Use xdotool to get active window on Linux."""
        # Get window ID
        win_id_result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=5
        )
        if win_id_result.returncode != 0:
            raise RuntimeError(win_id_result.stderr.strip())

        win_id = win_id_result.stdout.strip()

        # Get window title
        title_result = subprocess.run(
            ["xdotool", "getwindowname", win_id],
            capture_output=True, text=True, timeout=5
        )
        window_title = title_result.stdout.strip() if title_result.returncode == 0 else ""

        # Get PID → process name
        pid_result = subprocess.run(
            ["xdotool", "getwindowpid", win_id],
            capture_output=True, text=True, timeout=5
        )
        app_name = "unknown"
        if pid_result.returncode == 0:
            try:
                import psutil
                proc = psutil.Process(int(pid_result.stdout.strip()))
                app_name = proc.name()
            except Exception:
                app_name = pid_result.stdout.strip()

        return {"app_name": app_name, "window_title": window_title}


# ─────────────────────────────────────────────
# Idle detection (cross-platform)
# ─────────────────────────────────────────────

class IdleDetector:
    """
    Detects system idle time using psutil or platform-specific calls.
    Falls back to always-active if no method is available.
    """

    def __init__(self):
        self._method = self._detect_method()
        log.info(f"Idle detection method: {self._method}")

    def _detect_method(self) -> str:
        sys_plat = platform.system()
        if sys_plat == "Darwin":
            return "ioreg"
        elif sys_plat == "Windows":
            try:
                import ctypes
                return "winapi"
            except Exception:
                return "none"
        elif sys_plat == "Linux":
            try:
                result = subprocess.run(
                    ["xprintidle"], capture_output=True, timeout=2
                )
                if result.returncode == 0:
                    return "xprintidle"
            except Exception:
                pass
        return "none"

    def get_idle_seconds(self) -> float:
        """Returns number of seconds since last user input. Returns 0 on failure."""
        try:
            if self._method == "ioreg":
                return self._ioreg_idle()
            elif self._method == "winapi":
                return self._winapi_idle()
            elif self._method == "xprintidle":
                return self._xprintidle_idle()
        except Exception as e:
            log.debug(f"Idle detection error: {e}")
        return 0

    def _ioreg_idle(self) -> float:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "HIDIdleTime" in line:
                idle_ns = int(line.split("=")[-1].strip())
                return idle_ns / 1e9
        return 0

    def _winapi_idle(self) -> float:
        import ctypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0

    def _xprintidle_idle(self) -> float:
        result = subprocess.run(
            ["xprintidle"], capture_output=True, text=True, timeout=3
        )
        return int(result.stdout.strip()) / 1000.0


# ─────────────────────────────────────────────
# JSONL writer
# ─────────────────────────────────────────────

class ActivityWriter:
    """Writes JSON Lines events to the daily activity log file."""

    def __init__(self):
        ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    def _today_path(self) -> Path:
        return ACTIVITY_DIR / f"{date.today().isoformat()}.jsonl"

    def write_event(self, event: dict):
        """Append a single event dict as a JSON line."""
        line = json.dumps(event, ensure_ascii=False)
        with open(self._today_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_today(self) -> list:
        """Read all events from today's log. Returns empty list if not found."""
        path = self._today_path()
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
# Core Logger
# ─────────────────────────────────────────────

class EVALogger:
    """
    Main logger class. Polls active window every POLL_INTERVAL seconds,
    detects idle, tracks sessions, and writes events to JSONL.
    """

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.session_id = str(uuid.uuid4())
        self.detector = WindowDetector()
        self.idle_detector = IdleDetector()
        self.writer = ActivityWriter()

        self._running = False
        self._idle = False
        self._last_app = None
        self._last_title = None
        self._last_event_time = datetime.now()

        # In-memory accumulators for the test mode report
        self._captured_events: list = []

    def _make_event(self, event_type: str, app_name: str = "",
                    window_title: str = "", duration_seconds: float = 0) -> dict:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event_type": event_type,
            "app_name": app_name,
            "window_title": window_title,
            "duration_seconds": round(duration_seconds, 1),
            "session_id": self.session_id,
        }

    def _emit(self, event: dict):
        """Write event to disk and optionally accumulate for test mode."""
        self.writer.write_event(event)
        if self.test_mode:
            self._captured_events.append(event)
        log.debug(f"Event: {event['event_type']} | {event['app_name']} | {event['window_title']}")

    def _session_start(self):
        event = self._make_event("session_start")
        self._emit(event)
        log.info(f"Session started: {self.session_id}")

    def _session_end(self):
        now = datetime.now()
        duration = (now - self._last_event_time).total_seconds()
        event = self._make_event("session_end", duration_seconds=duration)
        self._emit(event)
        log.info(f"Session ended: {self.session_id}")

    def _poll(self):
        """Single poll cycle: check window, check idle, emit events."""
        now = datetime.now()
        idle_secs = self.idle_detector.get_idle_seconds()

        # ── Idle transition ──────────────────────────────
        if idle_secs >= IDLE_THRESHOLD and not self._idle:
            self._idle = True
            duration = (now - self._last_event_time).total_seconds()
            event = self._make_event(
                "idle_start",
                app_name=self._last_app or "",
                duration_seconds=duration,
            )
            self._emit(event)
            self._last_event_time = now
            log.info("Idle detected")
            return

        if self._idle and idle_secs < IDLE_THRESHOLD:
            self._idle = False
            event = self._make_event("idle_end")
            self._emit(event)
            self._last_event_time = now
            log.info("Idle ended — user returned")

        if self._idle:
            return  # Don't track window while idle

        # ── Window focus ─────────────────────────────────
        win = self.detector.get_active_window()
        app_name = win["app_name"]
        window_title = win["window_title"]

        # Context switch: app or title changed
        if app_name != self._last_app or window_title != self._last_title:
            duration = (now - self._last_event_time).total_seconds()

            # Emit focus event for the previous app (if any)
            if self._last_app is not None:
                event = self._make_event(
                    "window_focus",
                    app_name=self._last_app,
                    window_title=self._last_title or "",
                    duration_seconds=duration,
                )
                self._emit(event)

            self._last_app = app_name
            self._last_title = window_title
            self._last_event_time = now

    def run(self, duration_seconds: float = None):
        """
        Main loop. Runs indefinitely unless duration_seconds is set (test mode).
        """
        self._running = True
        self._session_start()
        start_time = time.monotonic()

        try:
            while self._running:
                try:
                    self._poll()
                except Exception as e:
                    log.error(f"Poll error (continuing): {e}")

                # Test mode: exit after duration
                if duration_seconds and (time.monotonic() - start_time) >= duration_seconds:
                    break

                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            log.info("Interrupt received")
        finally:
            self._session_end()
            self._running = False

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────
# Test mode report
# ─────────────────────────────────────────────

def run_test_mode():
    """Run logger for 60 seconds and print a structured report."""
    print("\n" + "═" * 60)
    print("  EVA LOGGER — TEST MODE (60 seconds)")
    print("═" * 60)
    print("Capturing activity... (switch a few apps to generate data)\n")

    logger = EVALogger(test_mode=True)
    logger.run(duration_seconds=60)

    events = logger._captured_events
    print("\n" + "═" * 60)
    print(f"  CAPTURED {len(events)} EVENTS")
    print("═" * 60)

    app_durations: dict = defaultdict(float)
    context_switches = 0
    idle_periods = 0

    for ev in events:
        etype = ev["event_type"]
        if etype == "window_focus":
            app_durations[ev["app_name"]] += ev["duration_seconds"]
            context_switches += 1
        elif etype == "idle_start":
            idle_periods += 1

    print("\nEvents log:")
    for ev in events:
        ts = ev["timestamp"].split("T")[1]
        print(f"  [{ts}] {ev['event_type']:20s} | {ev['app_name']:20s} | {ev['window_title'][:40]}")

    print(f"\nApp time (seconds):")
    for app, secs in sorted(app_durations.items(), key=lambda x: -x[1]):
        print(f"  {app:25s} {secs:6.1f}s")

    print(f"\nContext switches : {context_switches}")
    print(f"Idle periods     : {idle_periods}")
    print(f"\nLog file         : {ACTIVITY_DIR / date.today().isoformat()}.jsonl")
    print("═" * 60 + "\n")


# ─────────────────────────────────────────────
# Signal handling
# ─────────────────────────────────────────────

_logger_instance: EVALogger = None

def _handle_signal(signum, frame):
    log.info(f"Signal {signum} received — shutting down gracefully")
    if _logger_instance:
        _logger_instance.stop()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test_mode()
    else:
        log.info("EVA Logger starting in daemon mode...")
        log.info(f"Data directory: {DATA_DIR}")
        log.info(f"Press Ctrl+C to stop")

        _logger_instance = EVALogger()
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
        _logger_instance.run()
