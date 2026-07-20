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
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = 8768
EVA_HOME   = Path.home() / "Eva"
START_SH   = EVA_HOME / "eva-start.sh"

LOG_DIR    = EVA_HOME / "logs"
STATUS_DIR = LOG_DIR / "status"

# Landing + Interest tracker (modules/intelligence/landing_tracker.py) caches its
# JSON here on every run; the /landing_status route serves that cache.
LANDING_TRACKER   = EVA_HOME / "modules" / "intelligence" / "landing_tracker.py"
LANDING_CACHE     = STATUS_DIR / "landing_tracker.json"

SERVICES = {
    "screenpipe":   {"cmd": "screenpipe",                                                       "port": 3030,  "health": None,                        "label": None},
    "logger":       {"cmd": f"cd {EVA_HOME}/modules/logger && python3 eva_logger.py",           "port": None,  "health": None, "pid_name": "eva_logger.py", "label": "logger"},
    "context_api":  {"cmd": f"cd {EVA_HOME}/modules/logger && python3 eva_context_api.py",      "port": 8765,  "health": "http://localhost:8765/health", "label": "context-api"},
    "deal_scout":   {"cmd": f"cd {EVA_HOME}/modules/deal-scout && python3 main.py",             "port": 8766,  "health": "http://localhost:8766/health", "label": "deal-scout"},
    "content_engine":{"cmd": f"cd {EVA_HOME}/modules/content-engine && python3 main.py",       "port": 8767,  "health": "http://localhost:8767/health", "label": "content-engine"},
    "channels":     {"cmd": f"cd {EVA_HOME}/modules/channels && python3 channels_api.py",       "port": 8770,  "health": "http://localhost:8770/health", "label": "channels"},
    "knowledge":    {"cmd": f"cd {EVA_HOME}/modules/knowledge && python3 knowledge_api.py",     "port": 8771,  "health": "http://localhost:8771/health", "label": "knowledge"},
    "voice":        {"cmd": f"cd {EVA_HOME}/modules/voice && python3 voice_service.py",         "port": 8774,  "health": "http://localhost:8774/health", "label": "voice"},
    "diracatron":   {"cmd": f"cd {EVA_HOME}/modules/triage-brain && python3 main.py",           "port": 8784,  "health": "http://localhost:8784/health", "label": "diracatron"},
    "treasurer":    {"cmd": f"cd {EVA_HOME}/modules/finance-tracker && python3 main.py",         "port": 8786,  "health": "http://localhost:8786/health", "label": "treasurer"},
    "social_scheduler":{"cmd": f"cd {EVA_HOME}/modules/social-scheduler && python3 main.py",     "port": 8787,  "health": "http://localhost:8787/health", "label": "social-scheduler"},
    "deployer":     {"cmd": f"cd {EVA_HOME}/modules/deployer && python3 main.py",                 "port": 8789,  "health": "http://localhost:8789/health", "label": "deployer"},
    "local_exec":   {"cmd": f"cd {EVA_HOME}/modules/local-exec && python3 main.py",               "port": 8790,  "health": "http://localhost:8790/health", "label": "local-exec"},
    "brand_builder":{"cmd": f"cd {EVA_HOME}/modules/brand-builder && python3 main.py",             "port": 8792,  "health": "http://localhost:8792/health", "label": "brand-builder"},
    "ip_scout":     {"cmd": f"cd {EVA_HOME}/modules/ip-scout && python3 main.py",                   "port": 8791,  "health": "http://localhost:8791/health", "label": "ip-scout"},
    "idea_generator":{"cmd": f"cd {EVA_HOME}/modules/idea-generator-agent && python3 main.py",     "port": 8793,  "health": "http://localhost:8793/idea/health", "label": "idea-generator-agent"},
    "trend_agent":{"cmd": f"cd {EVA_HOME}/modules/trend-agent && python3 main.py",             "port": 8788,  "health": "http://localhost:8788/health", "label": "trend-agent"},
    "video_generator":{"cmd": f"cd {EVA_HOME}/modules/video-generator && python3 main.py",     "port": 8794,  "health": "http://localhost:8794/health", "label": "video-generator"},
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


@app.get("/landing_status")
def landing_status(refresh: bool = False):
    """Serve the Landing + Interest tracker report.

    Reads the cached JSON the tracker writes on each run. With ``?refresh=1``
    (or when no cache exists) it runs the tracker once to regenerate. Landing
    checks + GHL lookups take a few seconds, so polling callers should hit this
    without ``refresh`` and let the scheduled tracker keep the cache warm.
    """
    import json as _json

    if refresh or not LANDING_CACHE.exists():
        if LANDING_TRACKER.exists():
            try:
                subprocess.run(
                    ["python3", str(LANDING_TRACKER), "--json"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(LANDING_TRACKER.parent),
                )
            except Exception:
                pass  # fall through to whatever cache exists

    if not LANDING_CACHE.exists():
        return {"available": False,
                "reason": "tracker has not run yet — run eva-landing-status.sh"}
    try:
        report = _json.loads(LANDING_CACHE.read_text())
        return {"available": True, **report}
    except (OSError, ValueError) as exc:
        return {"available": False, "reason": f"cache unreadable: {exc}"}


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


# ── Social approve-then-publish gate ───────────────────────────────────────────
# Delegates to modules/social-publish. Imported lazily so a missing dep never
# breaks the launcher's core service-management routes.

_SOCIAL_DIR = EVA_HOME / "modules" / "social-publish"


def _social_gate():
    """Import the social-publish gate on demand. Returns (gate, error)."""
    import sys as _sys
    if str(_SOCIAL_DIR) not in _sys.path:
        _sys.path.insert(0, str(_SOCIAL_DIR))
    try:
        import gate as _gate  # noqa: PLC0415
        return _gate, None
    except Exception as exc:  # ImportError / missing dep
        return None, f"social-publish module unavailable: {exc}"


class SocialSubmit(BaseModel):
    text: str
    image_path: Optional[str] = ""
    platforms: Optional[list] = None


@app.get("/social/creds")
def social_creds():
    """LinkedIn + X credential status (nothing secret is returned)."""
    import sys as _sys
    if str(_SOCIAL_DIR) not in _sys.path:
        _sys.path.insert(0, str(_SOCIAL_DIR))
    try:
        import credentials as _credentials  # noqa: PLC0415
        return _credentials.detect()
    except Exception as exc:
        return {"error": f"social-publish module unavailable: {exc}"}


@app.post("/social/submit")
def social_submit(body: SocialSubmit):
    """Record a draft and post it to Slack for approval. Does NOT publish."""
    gate, err = _social_gate()
    if err:
        return {"ok": False, "error": err}
    return gate.submit_for_approval(
        body.text,
        image_path=body.image_path or "",
        platforms=body.platforms,
    )


@app.post("/social/approve/{draft_id}")
def social_approve(draft_id: str):
    """Explicit approval → publish to LinkedIn + X. The Slack link target."""
    gate, err = _social_gate()
    if err:
        return {"ok": False, "error": err}
    return gate.approve(draft_id, actor="launcher-endpoint", via="endpoint")


@app.post("/social/reject/{draft_id}")
def social_reject(draft_id: str):
    gate, err = _social_gate()
    if err:
        return {"ok": False, "error": err}
    return gate.reject(draft_id, actor="launcher-endpoint")


@app.get("/social/status/{draft_id}")
def social_status(draft_id: str):
    import sys as _sys
    if str(_SOCIAL_DIR) not in _sys.path:
        _sys.path.insert(0, str(_SOCIAL_DIR))
    try:
        import store as _store  # noqa: PLC0415
        draft = _store.get_draft(draft_id)
        return draft or {"error": f"draft {draft_id} not found"}
    except Exception as exc:
        return {"error": f"social-publish module unavailable: {exc}"}


@app.post("/social/check-approvals")
def social_check_approvals():
    """Poll Slack for ✅/`approve` on pending drafts and publish approved ones."""
    gate, err = _social_gate()
    if err:
        return {"ok": False, "error": err}
    return {"processed": gate.check_slack_approvals()}


# ── Apollo → GHL cold-outreach pipeline ────────────────────────────────────────
# Delegates to modules/channels (apollo_connector + apollo_gate). Imported
# lazily so a missing dep never breaks the launcher's core service routes.

_CHANNELS_DIR = EVA_HOME / "modules" / "channels"


def _channels_path():
    import sys as _sys
    if str(_CHANNELS_DIR) not in _sys.path:
        _sys.path.insert(0, str(_CHANNELS_DIR))


def _apollo_gate():
    """Import the Apollo gate on demand. Returns (gate, error)."""
    _channels_path()
    try:
        import apollo_gate as _gate  # noqa: PLC0415
        return _gate, None
    except Exception as exc:
        return None, f"apollo module unavailable: {exc}"


class ApolloExtract(BaseModel):
    query: Optional[str] = ""
    max_contacts: Optional[int] = 100


@app.get("/apollo/creds")
def apollo_creds():
    """Apollo credential status (nothing secret is returned)."""
    _channels_path()
    try:
        import apollo_connector as _apollo  # noqa: PLC0415
        return _apollo.creds_status()
    except Exception as exc:
        return {"error": f"apollo module unavailable: {exc}"}


@app.get("/apollo/search")
def apollo_search(q: str = ""):
    """One page of live Apollo People search (preview; no staging/enrol)."""
    _channels_path()
    try:
        import apollo_connector as _apollo  # noqa: PLC0415
        return _apollo.search_people(q)
    except Exception as exc:
        return {"ok": False, "error": f"apollo module unavailable: {exc}"}


@app.post("/apollo/extract")
def apollo_extract(body: ApolloExtract):
    """Extract + dedup + stage a batch to Slack for approval. Does NOT enrol."""
    gate, err = _apollo_gate()
    if err:
        return {"ok": False, "error": err}
    return gate.extract_and_stage(body.query or "",
                                  max_contacts=body.max_contacts or 100)


@app.get("/apollo/batch/{batch_id}")
def apollo_batch(batch_id: str):
    _channels_path()
    try:
        import apollo_store as _store  # noqa: PLC0415
        batch = _store.get_batch(batch_id)
        return batch or {"error": f"batch {batch_id} not found"}
    except Exception as exc:
        return {"error": f"apollo module unavailable: {exc}"}


@app.post("/apollo/enroll/{batch_id}")
def apollo_enroll(batch_id: str):
    """Explicit approval → enrol the batch into GHL (fires the 7-touch)."""
    gate, err = _apollo_gate()
    if err:
        return {"ok": False, "error": err}
    return gate.approve(batch_id, actor="launcher-endpoint", via="endpoint")


@app.post("/apollo/check-approvals")
def apollo_check_approvals():
    """Poll Slack for ✅/`approve` on pending batches and enrol approved ones."""
    gate, err = _apollo_gate()
    if err:
        return {"ok": False, "error": err}
    return {"processed": gate.check_slack_approvals()}


# ── Agent Builder meta-agent ───────────────────────────────────────────────────
# Delegates to modules/agent-builder (catalog / scaffold / capture). Imported
# lazily so a missing dep never breaks the launcher's core service routes.

_AGENT_BUILDER_DIR = EVA_HOME / "modules" / "agent-builder"


def _agent_builder():
    """Import the agent_builder module on demand. Returns (module, error)."""
    import sys as _sys
    if str(_AGENT_BUILDER_DIR) not in _sys.path:
        _sys.path.insert(0, str(_AGENT_BUILDER_DIR))
    try:
        import agent_builder as _ab  # noqa: PLC0415
        return _ab, None
    except Exception as exc:
        return None, f"agent-builder module unavailable: {exc}"


class ScaffoldRequest(BaseModel):
    name: str
    purpose: Optional[str] = ""
    port: Optional[int] = None
    with_launchd: Optional[bool] = False
    notify: Optional[bool] = False


class CaptureRequest(BaseModel):
    name: str
    steps: list
    trigger: Optional[str] = "manual"
    summary: Optional[str] = ""
    inputs: Optional[list] = None
    module: Optional[str] = ""
    notify: Optional[bool] = False


@app.get("/agent-builder/catalog")
def agent_builder_catalog(write: bool = False):
    """Inventory every existing agent/module. ?write=1 refreshes the catalog md."""
    ab, err = _agent_builder()
    if err:
        return {"ok": False, "error": err}
    return ab.catalog(write=write)


@app.post("/agent-builder/scaffold")
def agent_builder_scaffold(body: ScaffoldRequest):
    """Scaffold a brand-new agent/module following the canonical Eva pattern."""
    ab, err = _agent_builder()
    if err:
        return {"ok": False, "error": err}
    return ab.scaffold(body.name, purpose=body.purpose or "", port=body.port,
                       with_launchd=bool(body.with_launchd), notify=bool(body.notify))


@app.post("/agent-builder/capture")
def agent_builder_capture(body: CaptureRequest):
    """Capture a one-off workflow as a repeatable SOP + Markdown runbook."""
    ab, err = _agent_builder()
    if err:
        return {"ok": False, "error": err}
    return ab.capture(body.name, steps=body.steps, trigger=body.trigger or "manual",
                      summary=body.summary or "", inputs=body.inputs,
                      module=body.module or "", notify=bool(body.notify))


# ── Diracatron top-level triage brain ─────────────────────────────────────────
# Delegates to modules/triage-brain (queue / run / dispatch). Imported lazily so
# a missing dep never breaks the launcher's core service routes. Diracatron sits
# ABOVE all other agents: it reads eva-state + activity + signals, ranks
# priorities, dispatches to downstream agents, and logs decisions back to
# eva-state so Eva learns.

_TRIAGE_DIR = EVA_HOME / "modules" / "triage-brain"


def _diracatron_service():
    """Import the Diracatron service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_TRIAGE_DIR) not in _sys.path:
        _sys.path.insert(0, str(_TRIAGE_DIR))
    try:
        from service import DiracatronService  # noqa: PLC0415
        return DiracatronService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"triage-brain module unavailable: {exc}"


class TriageDispatch(BaseModel):
    # Eva's dispatch brain: a free-form goal, or one queued item id.
    goal: Optional[str] = None
    item_id: Optional[str] = None
    context: Optional[dict] = None


@app.get("/triage/queue")
def triage_queue():
    """Diracatron's current ranked, still-open triage queue."""
    svc, err = _diracatron_service()
    if err:
        return {"ok": False, "error": err}
    return svc.queue()


@app.post("/triage/run")
def triage_run():
    """Run one Diracatron triage pass (ingest open doors → stack-rank)."""
    svc, err = _diracatron_service()
    if err:
        return {"ok": False, "error": err}
    return svc.run_pass()


@app.post("/triage/dispatch")
def triage_dispatch(body: TriageDispatch):
    """Eva's dispatch brain: {goal} → decide which lobes to invoke → fire → log.
    Also accepts {item_id} to dispatch a specific already-queued item."""
    svc, err = _diracatron_service()
    if err:
        return {"ok": False, "error": err}
    if body.goal:
        return svc.dispatch_goal(body.goal, context=body.context)
    if body.item_id:
        return svc.dispatch(body.item_id)
    return {"ok": False, "error": "goal or item_id is required"}


@app.post("/triage/digest")
def triage_digest():
    """Diracatron's prioritized stack-rank of open doors (nightly digest)."""
    svc, err = _diracatron_service()
    if err:
        return {"ok": False, "error": err}
    return svc.digest()


@app.get("/triage/registry")
def triage_registry():
    """The data-driven agent registry — every lobe Diracatron orchestrates."""
    svc, err = _diracatron_service()
    if err:
        return {"ok": False, "error": err}
    return {"count": len(svc.registry.slugs()), "agents": svc.registry.to_catalog()}


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


# ── Treasurer finance / spend tracker ──────────────────────────────────────────
# Delegates to modules/finance-tracker. Imported lazily so a missing dep never
# breaks the launcher's core service-management routes.

_FINANCE_DIR = EVA_HOME / "modules" / "finance-tracker"


def _treasurer():
    """Import the Treasurer service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_FINANCE_DIR) not in _sys.path:
        _sys.path.insert(0, str(_FINANCE_DIR))
    try:
        from service import TreasurerService  # noqa: PLC0415
        return TreasurerService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"finance-tracker module unavailable: {exc}"


class FinanceTrack(BaseModel):
    category: str
    amount_cents: int
    vendor: Optional[str] = ""
    source_agent: Optional[str] = ""
    note: Optional[str] = ""
    timestamp: Optional[str] = None
    event_key: Optional[str] = None


class FinanceBudget(BaseModel):
    category: str
    cap_cents: int
    period: Optional[str] = "month"


@app.post("/finance/track")
def finance_track(body: FinanceTrack):
    """Log a spend event; alerts if it crosses its category budget threshold."""
    svc, err = _treasurer()
    if err:
        return {"ok": False, "error": err}
    return svc.track(category=body.category, amount_cents=body.amount_cents,
                     vendor=body.vendor or "", source_agent=body.source_agent or "",
                     note=body.note or "", timestamp=body.timestamp,
                     event_key=body.event_key)


@app.get("/finance/summary")
def finance_summary(period: str = "month"):
    """Spend by category for the period (day / week / month)."""
    svc, err = _treasurer()
    if err:
        return {"error": err}
    return svc.summary(period)


@app.get("/finance/budget")
def finance_budget(period: Optional[str] = None):
    """Budget caps vs actual, with per-category usage status."""
    svc, err = _treasurer()
    if err:
        return {"error": err}
    return svc.budget(period)


@app.post("/finance/budget")
def finance_set_budget(body: FinanceBudget):
    """Set / update a category's budget cap."""
    svc, err = _treasurer()
    if err:
        return {"ok": False, "error": err}
    return svc.set_budget(category=body.category, cap_cents=body.cap_cents,
                          period=body.period or "month")


@app.get("/finance/export")
def finance_export():
    """CSV dump of every spend event."""
    svc, err = _treasurer()
    if err:
        return {"error": err}
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415
    return PlainTextResponse(content=svc.export_csv(), media_type="text/csv")


@app.get("/finance/burn")
def finance_burn():
    """Current-month run-rate projection vs total monthly budget."""
    svc, err = _treasurer()
    if err:
        return {"error": err}
    return svc.burn()


# ── Social-Scheduler daily LinkedIn + X publisher ──────────────────────────────
# Delegates to modules/social-scheduler. Imported lazily so a missing dep never
# breaks the launcher's core service-management routes. The 5-slot ET schedule,
# social-publish Slack gate, LIKE + CTA, and unified local-sqlite analytics all
# live in the module; this just exposes its surface on :8768.

_SOCIAL_SCHEDULER_DIR = EVA_HOME / "modules" / "social-scheduler"


def _social_scheduler():
    """Import the Social-Scheduler service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_SOCIAL_SCHEDULER_DIR) not in _sys.path:
        _sys.path.insert(0, str(_SOCIAL_SCHEDULER_DIR))
    try:
        from service import SocialSchedulerService  # noqa: PLC0415
        return SocialSchedulerService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"social-scheduler module unavailable: {exc}"


class ScheduleSeed(BaseModel):
    scheduled_date: Optional[str] = None


@app.get("/schedule")
def schedule_view():
    """The content queue grouped by status + the fixed ET slot schedule."""
    svc, err = _social_scheduler()
    if err:
        return {"error": err}
    return svc.schedule()


@app.post("/schedule/seed")
def schedule_seed(body: ScheduleSeed | None = None):
    """Pre-seed the day-1 content queue (idempotent, deduped by headline)."""
    svc, err = _social_scheduler()
    if err:
        return {"ok": False, "error": err}
    return svc.seed(scheduled_date=(body.scheduled_date if body else None))


@app.post("/schedule/run")
def schedule_run():
    """One scheduler pass: submit due posts, publish approved ones, prune."""
    svc, err = _social_scheduler()
    if err:
        return {"ok": False, "error": err}
    return svc.run()


@app.post("/schedule/sync")
def schedule_sync(window_days: int = 30):
    """Sync engagement metrics into the unified local analytics store."""
    svc, err = _social_scheduler()
    if err:
        return {"ok": False, "error": err}
    return svc.sync_analytics(window_days=window_days)


@app.get("/analytics")
def schedule_analytics():
    """Latest engagement snapshot per (platform, post) + totals."""
    svc, err = _social_scheduler()
    if err:
        return {"error": err}
    return svc.analytics()


# ── Deployer CI/CD self-update agent ───────────────────────────────────────────
# Delegates to modules/deployer. Imported lazily so a missing dep never breaks
# the launcher's core service-management routes. The 5-hour GitHub poll, safe
# fast-forward-only pull, changed-service diff, in-flight-gated restart, and
# eva-state emits all live in the module; this just exposes its surface on :8768.

_DEPLOYER_DIR = EVA_HOME / "modules" / "deployer"


def _deployer_service():
    """Import the Deployer service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_DEPLOYER_DIR) not in _sys.path:
        _sys.path.insert(0, str(_DEPLOYER_DIR))
    try:
        from service import DeployerService  # noqa: PLC0415
        return DeployerService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"deployer module unavailable: {exc}"


@app.get("/deployer/status")
def deployer_status():
    """Current local SHA, last check time, and last deploy result."""
    svc, err = _deployer_service()
    if err:
        return {"error": err}
    return svc.status()


@app.post("/deployer/check")
def deployer_check():
    """Manually trigger one poll → safe self-deploy pass."""
    svc, err = _deployer_service()
    if err:
        return {"ok": False, "error": err}
    return svc.check()


@app.get("/deployer/history")
def deployer_history(limit: int = 20):
    """Recent deploy passes, newest first."""
    svc, err = _deployer_service()
    if err:
        return {"error": err}
    return svc.history(limit=limit)


# ── Local-Exec "Mac hands" layer ───────────────────────────────────────────────
# Delegates to modules/local-exec. Imported lazily so a missing dep never breaks
# the launcher's core service-management routes. The allowlist, secret masking,
# one-tap Slack approval gate, sqlite audit, and eva-state emits all live in the
# module; this just exposes its localhost-only surface on :8768 too.

_LOCAL_EXEC_DIR = EVA_HOME / "modules" / "local-exec"


def _local_exec_service():
    """Import the Local-Exec service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_LOCAL_EXEC_DIR) not in _sys.path:
        _sys.path.insert(0, str(_LOCAL_EXEC_DIR))
    try:
        from service import LocalExecService  # noqa: PLC0415
        return LocalExecService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"local-exec module unavailable: {exc}"


class LocalExecRequest(BaseModel):
    command: str
    args: Optional[list] = None
    cwd: Optional[str] = None
    triggered_by: Optional[str] = "launcher-endpoint"
    timeout: Optional[int] = None


class LocalExecApprove(BaseModel):
    run_id: str
    approved: bool


@app.post("/local-exec/exec")
def local_exec_exec(body: LocalExecRequest):
    """Run an allowlisted command now, or gate a non-allowlisted one for approval."""
    svc, err = _local_exec_service()
    if err:
        return {"ok": False, "error": err}
    return svc.exec_command(body.command, body.args or [], cwd=body.cwd,
                            triggered_by=body.triggered_by or "launcher-endpoint",
                            timeout=body.timeout)


@app.get("/local-exec/status")
def local_exec_status():
    """Service health + allowlist summary + run counts by status."""
    svc, err = _local_exec_service()
    if err:
        return {"error": err}
    return svc.status()


@app.get("/local-exec/history")
def local_exec_history(limit: int = 20):
    """Recent audited runs, newest first."""
    svc, err = _local_exec_service()
    if err:
        return {"error": err}
    return svc.history(limit=limit)


@app.post("/local-exec/approve")
def local_exec_approve(body: LocalExecApprove):
    """Approve or deny a pending non-allowlisted run (one-tap gate)."""
    svc, err = _local_exec_service()
    if err:
        return {"ok": False, "error": err}
    return svc.approve(body.run_id, body.approved, actor="launcher-endpoint")


@app.post("/local-exec/approve/{run_id}")
def local_exec_approve_link(run_id: str, approved: bool = True):
    """Approval link target (posted to Slack)."""
    svc, err = _local_exec_service()
    if err:
        return {"ok": False, "error": err}
    return svc.approve(run_id, approved, actor="launcher-endpoint")


# ── Brand-Builder strategy/orchestration layer ─────────────────────────────────
# Delegates to modules/brand-builder. Imported lazily so a missing dep never
# breaks the launcher's core routes. The Brand Builder sits ABOVE content-engine
# (:8767) and social-scheduler (:8787): it writes content briefs and never posts,
# emitting brand_brief_created events for content-engine to pick up. This just
# exposes its /brand/* surface on :8768 too.

_BRAND_BUILDER_DIR = EVA_HOME / "modules" / "brand-builder"


def _brand_builder_service():
    """Import the Brand-Builder service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_BRAND_BUILDER_DIR) not in _sys.path:
        _sys.path.insert(0, str(_BRAND_BUILDER_DIR))
    try:
        from service import BrandBuilderService  # noqa: PLC0415
        return BrandBuilderService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"brand-builder module unavailable: {exc}"


class BrandPlanRequest(BaseModel):
    pipeline_id: str
    timeframe: str = "week"
    start_date: Optional[str] = None


class BrandQueueRequest(BaseModel):
    brief_ids: Optional[list] = None
    pipeline_id: Optional[str] = None


class BrandSeedRequest(BaseModel):
    pipeline_id: Optional[str] = None
    md_path: Optional[str] = None


@app.get("/brand/status")
def brand_status():
    """Pipelines / blueprints / personas / pending briefs / stale blueprints."""
    svc, err = _brand_builder_service()
    if err:
        return {"error": err}
    return svc.status()


@app.get("/brand/pipelines")
def brand_pipelines():
    """All strategy pipelines."""
    svc, err = _brand_builder_service()
    if err:
        return {"error": err}
    return {"pipelines": svc.list_pipelines()}


@app.get("/brand/pipelines/{pipeline_id}")
def brand_pipeline(pipeline_id: str):
    """One pipeline by id."""
    svc, err = _brand_builder_service()
    if err:
        return {"error": err}
    p = svc.get_pipeline(pipeline_id)
    return p if p is not None else {"error": f"unknown pipeline: {pipeline_id}"}


@app.get("/brand/blueprints/{category}")
def brand_blueprint(category: str):
    """One market blueprint by category name or slug."""
    svc, err = _brand_builder_service()
    if err:
        return {"error": err}
    b = svc.get_blueprint(category)
    return b if b is not None else {"error": f"unknown blueprint: {category}"}


@app.post("/brand/seed")
def brand_seed(body: BrandSeedRequest | None = None):
    """Seed a pipeline from the blueprint markdown."""
    svc, err = _brand_builder_service()
    if err:
        return {"ok": False, "error": err}
    kwargs = {}
    if body and body.pipeline_id:
        kwargs["pipeline_id"] = body.pipeline_id
    if body and body.md_path:
        kwargs["md_path"] = body.md_path
    return svc.seed(**kwargs)


@app.post("/brand/plan")
def brand_plan(body: BrandPlanRequest):
    """Weekly content plan → list of briefs."""
    svc, err = _brand_builder_service()
    if err:
        return {"ok": False, "error": err}
    return svc.plan(pipeline_id=body.pipeline_id, timeframe=body.timeframe,
                    start_date=body.start_date)


@app.get("/brand/briefs")
def brand_briefs(status: Optional[str] = None):
    """Pending / queued briefs."""
    svc, err = _brand_builder_service()
    if err:
        return {"error": err}
    return {"briefs": svc.list_briefs(status=status)}


@app.post("/brand/queue")
def brand_queue(body: BrandQueueRequest | None = None):
    """Emit briefs to content-engine via brand_brief_created events."""
    svc, err = _brand_builder_service()
    if err:
        return {"ok": False, "error": err}
    return svc.queue(brief_ids=(body.brief_ids if body else None),
                     pipeline_id=(body.pipeline_id if body else None))


@app.post("/brand/refresh")
def brand_refresh():
    """Re-check blueprints for staleness (>7d → brand_blueprint_stale)."""
    svc, err = _brand_builder_service()
    if err:
        return {"ok": False, "error": err}
    return svc.refresh()


# ── IP-Scout prior-art triage layer ────────────────────────────────────────────
# Delegates to modules/ip-scout. Imported lazily so a missing dep never breaks
# the launcher's core routes. IP-Scout is L1 autonomy: it triages invention-idea
# seeds against prior art and reports what's worth a patent attorney's review — it
# NEVER files or submits anything. This just exposes its /ip/* surface on :8768.

_IP_SCOUT_DIR = EVA_HOME / "modules" / "ip-scout"


def _ip_scout_service():
    """Import the IP-Scout service on demand. Returns (service, error)."""
    import sys as _sys
    if str(_IP_SCOUT_DIR) not in _sys.path:
        _sys.path.insert(0, str(_IP_SCOUT_DIR))
    try:
        from service import IPScoutService  # noqa: PLC0415
        return IPScoutService(), None
    except Exception as exc:  # ImportError / missing dep
        return None, f"ip-scout module unavailable: {exc}"


class IPSeedRequest(BaseModel):
    title: str
    description: str = ""
    category: str = "uncategorized"
    idea_id: Optional[str] = None


class IPScanRequest(BaseModel):
    report_date: Optional[str] = None
    mine: bool = True


@app.get("/ip/status")
def ip_status():
    """Sensors / idea counts / last run / reports."""
    svc, err = _ip_scout_service()
    if err:
        return {"error": err}
    return svc.status()


@app.get("/ip/ideas")
def ip_ideas(status: Optional[str] = None):
    """All invention-idea seeds (optional ?status=pending|triaged)."""
    svc, err = _ip_scout_service()
    if err:
        return {"error": err}
    return {"ideas": svc.list_ideas(status=status)}


@app.get("/ip/idea/{idea_id}")
def ip_idea(idea_id: str):
    """One idea + its latest disclosure."""
    svc, err = _ip_scout_service()
    if err:
        return {"error": err}
    idea = svc.get_idea(idea_id)
    return idea if idea is not None else {"error": f"unknown idea: {idea_id}"}


@app.post("/ip/seed")
def ip_seed(body: IPSeedRequest):
    """Add an invention idea seed."""
    svc, err = _ip_scout_service()
    if err:
        return {"ok": False, "error": err}
    return svc.seed_idea(title=body.title, description=body.description,
                         category=body.category, idea_id=body.idea_id)


@app.post("/ip/scan")
def ip_scan(body: IPScanRequest | None = None):
    """Trigger a prior-art triage run over pending ideas."""
    svc, err = _ip_scout_service()
    if err:
        return {"ok": False, "error": err}
    return svc.scan(report_date=(body.report_date if body else None),
                    mine=(body.mine if body else True))


@app.get("/ip/history")
def ip_history(limit: Optional[int] = None):
    """Past triage runs (newest first)."""
    svc, err = _ip_scout_service()
    if err:
        return {"error": err}
    return {"runs": svc.history(limit=limit)}


@app.get("/ip/report/{report_date}", response_class=PlainTextResponse)
def ip_report(report_date: str):
    """The daily markdown triage report for a date (YYYY-MM-DD)."""
    svc, err = _ip_scout_service()
    if err:
        return PlainTextResponse(err, status_code=503)
    md = svc.get_report(report_date)
    if md is None:
        return PlainTextResponse(f"No report for {report_date}", status_code=404)
    return md


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
