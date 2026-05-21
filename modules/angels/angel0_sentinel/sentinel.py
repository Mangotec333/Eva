#!/usr/bin/env python3
# Sentinel — EVA Angel 0 | Roman: eternal watcher | Auto-restarts dead services

import socket
import subprocess
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# ── Service Map: port → (name, start_script) ────────────────────
SERVICE_MAP = {
    8765: ("context-api",    "~/Eva/modules/context-api/start.sh"),
    8766: ("deal-scout",     "~/Eva/modules/deal-scout/start.sh"),
    8767: ("content-engine", "~/Eva/modules/content-engine/start.sh"),
    8768: ("launcher",       "~/Eva/modules/launcher/start.sh"),
    8769: ("lovable-bridge", "~/Eva/modules/lovable-bridge/start.sh"),
    8770: ("channels",       "~/Eva/modules/channels/start.sh"),
    8771: ("knowledge",      "~/Eva/modules/knowledge/start.sh"),
}

# ── Paths ────────────────────────────────────────────────────────
EVA_ANGELS_DIR = Path.home() / ".eva" / "angels"
LOG_FILE       = EVA_ANGELS_DIR / "sentinel_log.jsonl"
STATUS_FILE    = EVA_ANGELS_DIR / "sentinel_status.json"
INSTALL_SCRIPT = Path.home() / "Eva" / "modules" / "autostart" / "eva-install-services.sh"

# ── State file for consecutive failure tracking ──────────────────
STATE_FILE = EVA_ANGELS_DIR / "sentinel_state.json"

CONNECT_TIMEOUT = 2  # seconds


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs():
    EVA_ANGELS_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    """Load persistent state (consecutive failure counts, last restarts)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    # Default state
    return {
        str(port): {"consecutive_failures": 0, "last_restart": None}
        for port in SERVICE_MAP
    }


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict):
    """Append a JSON line to the sentinel log."""
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


def check_port(port: int) -> bool:
    """Return True if port is accepting connections."""
    try:
        with socket.create_connection(("localhost", port), timeout=CONNECT_TIMEOUT):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def restart_service(port: int, name: str, script_path: str) -> bool:
    """Run the service's start.sh in the background. Returns True if launched."""
    expanded = os.path.expanduser(script_path)
    if not os.path.isfile(expanded):
        log_event({
            "ts": now_iso(),
            "level": "ERROR",
            "event": "restart_skipped",
            "port": port,
            "service": name,
            "reason": f"start.sh not found: {expanded}",
        })
        return False

    try:
        subprocess.Popen(
            ["bash", expanded],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log_event({
            "ts": now_iso(),
            "level": "INFO",
            "event": "restart_attempted",
            "port": port,
            "service": name,
            "script": expanded,
        })
        return True
    except Exception as e:
        log_event({
            "ts": now_iso(),
            "level": "ERROR",
            "event": "restart_failed",
            "port": port,
            "service": name,
            "error": str(e),
        })
        return False


def run_install_script():
    """Run eva-install-services.sh if it exists (bootstrap fallback)."""
    script = str(INSTALL_SCRIPT)
    if not INSTALL_SCRIPT.exists():
        log_event({
            "ts": now_iso(),
            "level": "WARN",
            "event": "install_skipped",
            "reason": f"install script not found: {script}",
        })
        return

    log_event({
        "ts": now_iso(),
        "level": "INFO",
        "event": "install_started",
        "script": script,
    })
    try:
        subprocess.Popen(
            ["bash", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log_event({
            "ts": now_iso(),
            "level": "INFO",
            "event": "install_launched",
            "script": script,
        })
    except Exception as e:
        log_event({
            "ts": now_iso(),
            "level": "ERROR",
            "event": "install_failed",
            "error": str(e),
        })


def write_status(services_snapshot: dict, online_count: int):
    """Write sentinel_status.json for the Command Center nav dots."""
    total = len(SERVICE_MAP)
    status_doc = {
        "checked_at": now_iso(),
        "services": services_snapshot,
        "online_count": online_count,
        "total_count": total,
        "all_healthy": online_count == total,
    }
    STATUS_FILE.write_text(json.dumps(status_doc, indent=2))
    return status_doc


def main():
    ensure_dirs()
    state = load_state()

    log_event({
        "ts": now_iso(),
        "level": "INFO",
        "event": "check_started",
        "services_watched": len(SERVICE_MAP),
    })

    services_snapshot = {}
    online_count = 0
    first_run = not STATUS_FILE.exists()

    # ── 1. Check every port ──────────────────────────────────────
    for port, (name, script) in SERVICE_MAP.items():
        key = str(port)
        is_up = check_port(port)
        port_state = state.setdefault(key, {"consecutive_failures": 0, "last_restart": None})

        if is_up:
            online_count += 1
            port_state["consecutive_failures"] = 0
            log_event({
                "ts": now_iso(),
                "level": "INFO",
                "event": "port_online",
                "port": port,
                "service": name,
            })
            services_snapshot[key] = {
                "name": name,
                "status": "online",
                "last_restart": port_state["last_restart"],
                "consecutive_failures": 0,
            }
        else:
            port_state["consecutive_failures"] += 1
            cf = port_state["consecutive_failures"]
            level = "CRITICAL" if cf >= 3 else "WARN"

            log_event({
                "ts": now_iso(),
                "level": level,
                "event": "port_offline",
                "port": port,
                "service": name,
                "consecutive_failures": cf,
            })

            # ── 2. Auto-restart ──────────────────────────────────
            restarted = restart_service(port, name, script)
            ts_restart = now_iso() if restarted else port_state["last_restart"]
            port_state["last_restart"] = ts_restart

            services_snapshot[key] = {
                "name": name,
                "status": "offline",
                "last_restart": ts_restart,
                "consecutive_failures": cf,
            }

    # ── 3. First-run bootstrap: fewer than 3 services up ────────
    if first_run and online_count < 3:
        log_event({
            "ts": now_iso(),
            "level": "INFO",
            "event": "bootstrap_trigger",
            "online_count": online_count,
            "reason": "first_run with <3 services online",
        })
        run_install_script()

    # ── 4. Write status JSON ─────────────────────────────────────
    status_doc = write_status(services_snapshot, online_count)

    # ── 5. Persist state ─────────────────────────────────────────
    save_state(state)

    log_event({
        "ts": now_iso(),
        "level": "INFO",
        "event": "check_complete",
        "online_count": online_count,
        "total_count": len(SERVICE_MAP),
        "all_healthy": status_doc["all_healthy"],
    })

    # ── Print summary to stdout (captured by launchd log) ────────
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    healthy_str = "ALL HEALTHY" if status_doc["all_healthy"] else f"{online_count}/{len(SERVICE_MAP)} online"
    print(f"[{ts}] Sentinel check complete — {healthy_str}")
    for key, info in services_snapshot.items():
        icon = "✓" if info["status"] == "online" else "✗"
        cf_str = f" (failures: {info['consecutive_failures']})" if info["consecutive_failures"] else ""
        print(f"  {icon} :{key} {info['name']}{cf_str}")


if __name__ == "__main__":
    main()
