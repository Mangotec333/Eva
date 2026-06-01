#!/usr/bin/env python3
"""
EVA Wake Daemon  —  v1.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAKE MODEL:
  Services (8765/8766/8767) ALWAYS run — nohup-style.
  No work is ever lost due to idle.

  Idle only pauses INPUT LISTENERS:
    - HID polling slows from 1s to 5s  (less CPU)
    - Audio sampling pauses            (mic released)
    - Screenpipe watchdog notified     (screen capture pauses)

  Services resume FULL poll rate the moment a keystroke,
  click, or audio burst is detected.

  Services ONLY stop on:
    - Explicit user command (SIGUSR2 / eva-stop.sh)
    - Machine shutdown (launchd handles gracefully)
    - Sentinel detecting a crash (auto-restarts)

Install (launchd agent):
    cp ~/Eva/modules/autostart/launchd/com.eva.wake-daemon.plist \
       ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.eva.wake-daemon.plist

Signals:
  SIGUSR1  ->  force active mode
  SIGUSR2  ->  force stop ALL services (explicit shutdown only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
IDLE_SLEEP_SECONDS   = 300      # 5 min no activity → sleep services
POLL_FAST_SECONDS    = 1        # poll interval when awake (keystroke detection)
POLL_SLEEP_SECONDS   = 5        # poll interval when sleeping (lighter CPU)
AUDIO_RMS_THRESHOLD  = 200      # RMS level considered "mic activity"
AUDIO_SAMPLE_SECONDS = 0.5      # how long to sample mic per check
CONNECT_TIMEOUT      = 2        # seconds for health-check TCP connect

EVA_HOME   = Path.home() / "Eva"
LOG_PATH   = EVA_HOME / "logs" / "eva-wake-daemon.log"
STATE_PATH = EVA_HOME / "logs" / "eva-wake-state.json"

# Services to wake/sleep — port → (name, start_script)
SERVICES = {
    8765: ("context-api",     EVA_HOME / "modules" / "logger"         / "eva_context_api.py"),
    8766: ("deal-scout",      EVA_HOME / "modules" / "deal-scout"     / "main.py"),
    8767: ("content-engine",  EVA_HOME / "modules" / "content-engine" / "main.py"),
}

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVA-WAKE] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("eva-wake")


# ── State ──────────────────────────────────────────────────────────────────────
class WakeState:
    """
    Two modes:
      ACTIVE  — user present, HID poll every 1s, audio sampling ON
      IDLE    — no input for >5min, HID poll every 5s, audio OFF, services UNTOUCHED

    Services NEVER stop due to idle. They are permanent background processes.
    """
    def __init__(self):
        self.active: bool = True        # start active, ensure services come up
        self.last_activity_ts: float = time.monotonic()
        self.force_active: bool = False
        self.force_shutdown: bool = False  # explicit only

    def touch(self):
        self.last_activity_ts = time.monotonic()
        if not self.active:
            self.active = True

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity_ts

    def save(self):
        try:
            STATE_PATH.write_text(json.dumps({
                "mode": "active" if self.active else "idle",
                "idle_seconds": round(self.idle_seconds(), 1),
                "services": "always_running",
                "last_activity": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception:
            pass


state = WakeState()


# ── Signal handlers ──────────────────────────────────────────────────────────
def _sig_active(signum, frame):
    log.info("SIGUSR1 -> force active mode")
    state.force_active = True

def _sig_shutdown(signum, frame):
    """Explicit shutdown only — NOT triggered by idle."""
    log.info("SIGUSR2 -> explicit shutdown requested")
    state.force_shutdown = True

signal.signal(signal.SIGUSR1, _sig_active)
signal.signal(signal.SIGUSR2, _sig_shutdown)


# ── Service control ───────────────────────────────────────────────────────────
# Services run PERMANENTLY. These functions only start them if not already up,
# or stop them on explicit SIGUSR2 shutdown. Never called due to idle.

_service_procs: dict[int, subprocess.Popen] = {}


def ensure_services_running():
    """Start any service that isn't already responding. Idempotent."""
    for port, (name, script) in SERVICES.items():
        if service_alive(port):
            continue
        log.info("  starting %s on :%d", name, port)
        log_file = EVA_HOME / "logs" / f"eva-{name}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ,
               "PYTHONPATH": str(script.parent) + ":" + os.environ.get("PYTHONPATH", "")}
        port_args = ["--port", str(port)] if name in ("deal-scout", "context-api") else []
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script)] + port_args,
                cwd=str(script.parent),
                env=env,
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True,   # nohup equivalent — survives terminal close
            )
            _service_procs[port] = proc
            log.info("  %s launched PID %d", name, proc.pid)
        except Exception as e:
            log.error("  failed to start %s: %s", name, e)


def shutdown_all_services():
    """Explicit shutdown only — called on SIGUSR2 or exit."""
    log.info("Shutting down all Eva services (explicit)")
    for port, (name, _) in SERVICES.items():
        if not service_alive(port):
            continue
        log.info("  stopping %s:%d", name, port)
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], timeout=5,
                           stderr=subprocess.DEVNULL)
        except Exception:
            pass
        proc = _service_procs.pop(port, None)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


# ── Activity detection ────────────────────────────────────────────────────────
def detect_activity() -> bool:
    """True if HID idle < 2s (just typed/clicked) or mic active."""
    if hid_idle_seconds() < 2.0:
        return True
    if state.active and has_audio_activity():   # only sample audio when active (mic release when idle)
        return True
    return False


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("EVA Wake Daemon v1.1 started | PID: %d", os.getpid())
    log.info("Model: services=ALWAYS_ON | idle throttles listener only | idle-threshold=%ds", IDLE_SLEEP_SECONDS)

    pid_file = EVA_HOME / "logs" / "eva-wake-daemon.pid"
    pid_file.write_text(str(os.getpid()))

    # Ensure services are up immediately on daemon start
    ensure_services_running()
    log.info("All services confirmed running.")

    save_tick = 0

    while True:
        try:
            # ── Explicit shutdown (SIGUSR2) ────────────────────────
            if state.force_shutdown:
                state.force_shutdown = False
                shutdown_all_services()
                break

            # ── Force active (SIGUSR1) ─────────────────────────────
            if state.force_active:
                state.force_active = False
                state.touch()
                log.info("Forced active mode")

            # ── Ensure services are still running ──────────────────
            # Sentinel also does this, but double-check every 60s
            if save_tick % 60 == 0:
                ensure_services_running()

            # ── Activity detection ─────────────────────────────────
            active = detect_activity()

            if active:
                was_idle = not state.active
                state.touch()          # sets active=True
                if was_idle:
                    log.info("Activity detected -> returning to active mode (HID idle=%.1fs)", hid_idle_seconds())
            else:
                idle = state.idle_seconds()
                if state.active and idle >= IDLE_SLEEP_SECONDS:
                    state.active = False
                    log.info("Idle %.0fs -> throttling listener (services still running)", idle)

            # ── Poll rate: fast when active, slow when idle ────────
            # Services keep running either way.
            poll = POLL_FAST_SECONDS if state.active else POLL_SLEEP_SECONDS

            save_tick += 1
            if save_tick % 12 == 0:
                state.save()

            time.sleep(poll)

        except KeyboardInterrupt:
            log.info("Wake Daemon stopped by user")
            break
        except Exception as e:
            log.error("Loop error: %s", e)
            time.sleep(5)

    pid_file.unlink(missing_ok=True)
    log.info("Eva Wake Daemon exited")


if __name__ == "__main__":
    main()
