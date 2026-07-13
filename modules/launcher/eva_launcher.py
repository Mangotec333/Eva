#!/usr/bin/env python3
"""
EVA Launcher — Module 7
Tiny FastAPI server on :8768 that lets the Command Center
start/stop/check EVA services with a single HTTP call.

Start manually:  python eva_launcher.py
Auto-start:      installed via eva-install-services.sh (launchd)
"""

import os
import subprocess
import time
import signal
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = 8768
EVA_HOME   = Path.home() / "Eva"
START_SH   = EVA_HOME / "eva-start.sh"

LOG_DIR    = EVA_HOME / "logs"
STATUS_DIR = LOG_DIR / "status"

SERVICES = {
    "screenpipe":   {"cmd": "screenpipe",                                                       "port": 3030,  "health": None,                        "label": None},
    "logger":       {"cmd": f"cd {EVA_HOME}/modules/logger && python3 eva_logger.py",           "port": None,  "health": None, "pid_name": "eva_logger.py", "label": "logger"},
    "context_api":  {"cmd": f"cd {EVA_HOME}/modules/logger && python3 eva_context_api.py",      "port": 8765,  "health": "http://localhost:8765/health", "label": "context-api"},
    "deal_scout":   {"cmd": f"cd {EVA_HOME}/modules/deal-scout && python3 main.py",             "port": 8766,  "health": "http://localhost:8766/health", "label": "deal-scout"},
    "content_engine":{"cmd": f"cd {EVA_HOME}/modules/content-engine && python3 main.py",       "port": 8767,  "health": "http://localhost:8767/health", "label": "content-engine"},
    "channels":     {"cmd": f"cd {EVA_HOME}/modules/channels && python3 channels_api.py",       "port": 8770,  "health": "http://localhost:8770/health", "label": "channels"},
    "knowledge":    {"cmd": f"cd {EVA_HOME}/modules/knowledge && python3 knowledge_api.py",     "port": 8771,  "health": "http://localhost:8771/health", "label": "knowledge"},
    "voice":        {"cmd": f"cd {EVA_HOME}/modules/voice && python3 voice_service.py",         "port": 8774,  "health": "http://localhost:8774/health", "label": "voice"},
}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="EVA Launcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def port_is_listening(port: int) -> bool:
    """Check if a TCP port is open without importing extra deps."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def pid_is_running(script_name: str) -> bool:
    """Check if a Python script is running by process name."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def read_status_file(label: Optional[str]) -> dict:
    """Read the key=value status file written by run-service.sh, if present."""
    if not label:
        return {}
    path = STATUS_DIR / f"{label}.status"
    if not path.exists():
        return {}
    data = {}
    try:
        for line in path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    except OSError:
        return {}
    return data


def service_status(name: str) -> str:
    info = SERVICES[name]
    port = info.get("port")
    pid_name = info.get("pid_name")
    if port:
        return "online" if port_is_listening(port) else "offline"
    if pid_name:
        return "online" if pid_is_running(pid_name) else "offline"
    # No port and no pid marker — fall back to the run-service.sh status file
    # instead of reporting a useless "unknown".
    sf = read_status_file(info.get("label"))
    state = sf.get("state")
    if state in ("running", "starting"):
        return "online"
    if state:
        return "offline"
    return "unknown"


def service_detail(name: str) -> dict:
    """Rich per-service diagnostics: verdict + last recorded state/reason."""
    info = SERVICES[name]
    sf = read_status_file(info.get("label"))
    return {
        "status": service_status(name),
        "port": info.get("port"),
        "state": sf.get("state"),
        "reason": sf.get("reason"),
        "last_update": sf.get("ts"),
    }


def all_statuses() -> dict:
    return {name: service_status(name) for name in SERVICES}


def all_details() -> dict:
    return {name: service_detail(name) for name in SERVICES}


def launch_in_terminal_tab(cmd: str):
    """Open a new macOS Terminal tab running cmd."""
    escaped = cmd.replace('"', '\\"').replace("'", "\\'")
    script = f'''
tell application "Terminal"
    activate
    tell application "System Events" to keystroke "t" using command down
    delay 0.4
    do script "{escaped}" in front window
end tell
'''
    subprocess.run(["osascript", "-e", script], check=False)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "online", "service": "eva_launcher", "port": PORT}


@app.get("/status")
def status():
    """Return live status of all EVA services."""
    statuses = all_statuses()
    online_count = sum(1 for s in statuses.values() if s == "online")
    return {
        "services": statuses,
        "details": all_details(),
        "online": online_count,
        "online_count": online_count,   # alias for older callers
        "total": len(SERVICES),
        "all_online": online_count == len(SERVICES),
        "timestamp": time.time(),
    }


@app.post("/start")
def start_all():
    """
    Launch all EVA services in macOS Terminal tabs.
    Uses eva-start.sh if it exists, otherwise opens tabs individually.
    """
    already = all_statuses()
    launched = []
    skipped  = []

    if START_SH.exists():
        # Run the master start script in a Terminal tab
        launch_in_terminal_tab(f"bash {START_SH}")
        launched = list(SERVICES.keys())
    else:
        # Fallback: open each service individually
        for name, info in SERVICES.items():
            if already.get(name) == "online":
                skipped.append(name)
                continue
            launch_in_terminal_tab(info["cmd"])
            launched.append(name)
            time.sleep(0.4)   # stagger tab opens

    # Brief pause then re-check statuses
    time.sleep(2)
    after = all_statuses()

    return {
        "action": "start",
        "launched": launched,
        "skipped_already_online": skipped,
        "statuses_after": after,
        "timestamp": time.time(),
    }


@app.post("/start/{service_name}")
def start_one(service_name: str):
    """Launch a single named service."""
    if service_name not in SERVICES:
        return {"error": f"Unknown service: {service_name}. Valid: {list(SERVICES.keys())}"}

    info = SERVICES[service_name]
    current = service_status(service_name)

    if current == "online":
        return {"action": "start", "service": service_name, "result": "already_online"}

    launch_in_terminal_tab(info["cmd"])
    time.sleep(2)
    after = service_status(service_name)

    return {
        "action": "start",
        "service": service_name,
        "result": "launched",
        "status_after": after,
        "timestamp": time.time(),
    }


@app.post("/stop/{service_name}")
def stop_one(service_name: str):
    """Kill a service by port (where applicable)."""
    if service_name not in SERVICES:
        return {"error": f"Unknown service: {service_name}"}

    port = SERVICES[service_name].get("port")
    if not port:
        return {"error": f"{service_name} has no port — stop it manually in its Terminal tab"}

    # Find PID listening on port via lsof
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        killed = []
        for pid_str in pids:
            try:
                os.kill(int(pid_str), signal.SIGTERM)
                killed.append(int(pid_str))
            except ProcessLookupError:
                pass

        time.sleep(1)
        after = service_status(service_name)
        return {
            "action": "stop",
            "service": service_name,
            "pids_killed": killed,
            "status_after": after,
            "timestamp": time.time(),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Terminal Exec ────────────────────────────────────────────────────────────

class ExecRequest(BaseModel):
    command: str
    timeout: Optional[int] = 30
    working_dir: Optional[str] = None


@app.post("/terminal/exec")
def terminal_exec(req: ExecRequest):
    """
    Execute a shell command on the Mac and return stdout/stderr.
    Runs in the user's shell environment (sources .zshrc).
    """
    # Build command that sources shell env first
    shell_cmd = f'source ~/.zshrc 2>/dev/null; {req.command}'
    cwd = req.working_dir or str(Path.home())

    start = time.time()
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", shell_cmd],
            capture_output=True,
            text=True,
            timeout=req.timeout,
            cwd=cwd,
        )
        duration_ms = int((time.time() - start) * 1000)
        return {
            "command": req.command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": req.command,
            "stdout": "",
            "stderr": f"Command timed out after {req.timeout}s",
            "exit_code": -1,
            "duration_ms": req.timeout * 1000,
        }
    except Exception as e:
        return {
            "command": req.command,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "duration_ms": int((time.time() - start) * 1000),
        }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"""
  ██╗      █████╗ ██╗   ██╗███╗   ██╗ ██████╗██╗  ██╗███████╗██████╗
  ██║     ██╔══██╗██║   ██║████╗  ██║██╔════╝██║  ██║██╔════╝██╔══██╗
  ██║     ███████║██║   ██║██╔██╗ ██║██║     ███████║█████╗  ██████╔╝
  ██║     ██╔══██║██║   ██║██║╚██╗██║██║     ██╔══██║██╔══╝  ██╔══██╗
  ███████╗██║  ██║╚██████╔╝██║ ╚████║╚██████╗██║  ██║███████╗██║  ██║
  ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
  EVA Launcher — Module 7  |  :8768
""")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
