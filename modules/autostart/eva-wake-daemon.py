#!/usr/bin/env python3
"""
EVA Wake Daemon  —  v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wakes Eva services the moment any keystroke / mouse click /
audio activity is detected.  Sleeps them after 5 minutes of
full inactivity (HID + audio both silent).

Install (launchd agent — runs at login):
    cp ~/Eva/modules/autostart/launchd/com.eva.wake-daemon.plist \
       ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.eva.wake-daemon.plist

Uninstall:
    launchctl unload ~/Library/LaunchAgents/com.eva.wake-daemon.plist

Manual run:
    python3 ~/Eva/modules/autostart/eva-wake-daemon.py

Signals:
  SIGUSR1  →  force wake  (launchctl kickstart can trigger this)
  SIGUSR2  →  force sleep
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
    def __init__(self):
        self.awake: bool = False
        self.last_activity_ts: float = 0.0
        self.force_wake: bool = False
        self.force_sleep: bool = False

    def touch(self):
        self.last_activity_ts = time.monotonic()

    def idle_seconds(self) -> float:
        if self.last_activity_ts == 0:
            return float("inf")
        return time.monotonic() - self.last_activity_ts

    def save(self):
        try:
            STATE_PATH.write_text(json.dumps({
                "awake": self.awake,
                "idle_seconds": round(self.idle_seconds(), 1),
                "last_activity": datetime.now(timezone.utc).isoformat()
                    if self.last_activity_ts > 0 else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception:
            pass


state = WakeState()


# ── Signal handlers ────────────────────────────────────────────────────────────
def _sig_wake(signum, frame):
    log.info("SIGUSR1 received → force wake")
    state.force_wake = True

def _sig_sleep(signum, frame):
    log.info("SIGUSR2 received → force sleep")
    state.force_sleep = True

signal.signal(signal.SIGUSR1, _sig_wake)
signal.signal(signal.SIGUSR2, _sig_sleep)


# ── HID idle detection (macOS ioreg) ──────────────────────────────────────────
def hid_idle_seconds() -> float:
    """Seconds since last keyboard or mouse event via ioreg."""
    try:
        out = subprocess.check_output(
            ["ioreg", "-c", "IOHIDSystem"],
            timeout=3, stderr=subprocess.DEVNULL
        ).decode()
        for line in out.splitlines():
            if "HIDIdleTime" in line:
                ns = int(line.split("=")[-1].strip())
                return ns / 1_000_000_000
    except Exception:
        pass
    return 0.0


# ── Audio activity detection ──────────────────────────────────────────────────
def has_audio_activity() -> bool:
    """
    Returns True if microphone RMS level exceeds threshold.
    Uses sounddevice if available; silently returns False if not.
    This is best-effort — voice detection is handled by the voice service.
    """
    try:
        import sounddevice as sd
        import numpy as np
        chunk = sd.rec(
            int(AUDIO_SAMPLE_SECONDS * 16000),
            samplerate=16000, channels=1, dtype="int16",
            blocking=True
        )
        rms = float(np.sqrt(np.mean(chunk.astype(float) ** 2)))
        return rms > AUDIO_RMS_THRESHOLD
    except Exception:
        return False


# ── Service health check ──────────────────────────────────────────────────────
def service_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


# ── Service control ───────────────────────────────────────────────────────────
_service_procs: dict[int, subprocess.Popen] = {}


def _start_service(port: int, name: str, script: Path):
    if service_alive(port):
        log.info(f"  {name}:{port} already up")
        return
    log.info(f"  starting {name} on :{port}")
    log_file = EVA_HOME / "logs" / f"eva-{name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(EVA_HOME / "modules" / name) + ":" + os.environ.get("PYTHONPATH", "")}

    # port arg only for services that accept --port
    port_args = ["--port", str(port)] if name in ("deal-scout", "context-api") else []

    proc = subprocess.Popen(
        [sys.executable, str(script)] + port_args,
        cwd=str(script.parent),
        env=env,
        stdout=open(log_file, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _service_procs[port] = proc
    log.info(f"  {name} launched PID {proc.pid}")


def _stop_service(port: int, name: str):
    if not service_alive(port):
        return
    log.info(f"  stopping {name}:{port}")
    # try graceful then force
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


def wake_services():
    if state.awake:
        return
    log.info("━━ WAKE ━━  starting Eva services")
    for port, (name, script) in SERVICES.items():
        try:
            _start_service(port, name, script)
        except Exception as e:
            log.error(f"  failed to start {name}: {e}")
    state.awake = True
    state.save()
    log.info("━━ Eva AWAKE ━━")


def sleep_services():
    if not state.awake:
        return
    log.info("━━ SLEEP ━━  stopping Eva services (5min idle)")
    for port, (name, _) in SERVICES.items():
        try:
            _stop_service(port, name)
        except Exception as e:
            log.error(f"  failed to stop {name}: {e}")
    state.awake = False
    state.save()
    log.info("━━ Eva SLEEPING ━━")


# ── Activity detection ────────────────────────────────────────────────────────
def detect_activity() -> bool:
    """Returns True if any HID or audio activity detected RIGHT NOW."""
    # Primary: HID idle < 2s = user just typed/clicked
    hid = hid_idle_seconds()
    if hid < 2.0:
        return True
    # Secondary: audio (best-effort, may be unavailable)
    if has_audio_activity():
        return True
    return False


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("EVA Wake Daemon started  |  idle-sleep threshold: %ds  |  PID: %d",
             IDLE_SLEEP_SECONDS, os.getpid())
    log.info("Services: %s", {v[0]: k for k, v in SERVICES.items()})

    # Write PID file so other scripts can send SIGUSR1/2
    pid_file = EVA_HOME / "logs" / "eva-wake-daemon.pid"
    pid_file.write_text(str(os.getpid()))

    consecutive_no_activity = 0

    while True:
        try:
            # ── Forced state overrides ─────────────────────────────
            if state.force_wake:
                state.force_wake = False
                state.touch()
                wake_services()

            if state.force_sleep:
                state.force_sleep = False
                sleep_services()

            # ── Normal activity detection ──────────────────────────
            active = detect_activity()

            if active:
                state.touch()
                consecutive_no_activity = 0

                if not state.awake:
                    log.info("Activity detected (HID idle=%.1fs) → waking", hid_idle_seconds())
                    wake_services()
            else:
                consecutive_no_activity += 1
                idle = state.idle_seconds()

                if state.awake and idle >= IDLE_SLEEP_SECONDS:
                    log.info("Idle for %.0fs (threshold %ds) → sleeping", idle, IDLE_SLEEP_SECONDS)
                    sleep_services()

            # ── Periodic state save ────────────────────────────────
            if consecutive_no_activity % 12 == 0:  # every ~1 min when sleeping
                state.save()

            # ── Poll interval ──────────────────────────────────────
            poll = POLL_FAST_SECONDS if state.awake else POLL_SLEEP_SECONDS
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
