"""
EVA Local-Exec — FastAPI microservice ("Mac hands")
====================================================
Port: 8790  |  Bind: 127.0.0.1 ONLY (loopback)

The generalized "hands" layer: a localhost-only service that lets Eva run shell
commands on the Mac, on demand, safely. A small allowlist of demonstrably-safe
ops auto-runs; everything else is gated behind a one-tap Slack approval. Every
run is secret-masked and fully audited (local sqlite + eva-state).

**This service is NEVER exposed via cloudflared / any tunnel.** It binds to
127.0.0.1 only, and a startup assertion *refuses to bind to 0.0.0.0* (or any
non-loopback host) so it can never be accidentally published.

Endpoints:
  GET  /health                 Health + offline flag + allowlist size
  POST /local-exec/exec        Run a command (allowlisted → now; else → gated)
  GET  /local-exec/status      Service health + allowlist summary + run counts
  GET  /local-exec/history     Recent audited runs (newest first, capped)
  POST /local-exec/approve     Approve/deny a pending non-allowlisted run

Offline-safe: ``EVA_LOCAL_EXEC_OFFLINE=1`` → /exec returns a mocked no-op and
never spawns a subprocess (the sandbox / test default).

Note: this is the generalized hands layer. The deployer's scoped CI/CD
(ff-only pull + restart / vercel --prod) is a *future consumer* of this exec
primitive, not a dependency.
"""

from __future__ import annotations

import argparse
import ipaddress

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from service import LocalExecService

AGENT_VERSION = "0.1.0"
PORT = 8790
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

service = LocalExecService()


def assert_localhost_bind(host: str) -> None:
    """Refuse to bind anywhere but loopback. NEVER 0.0.0.0 / a routable IP.

    This is the single hard guarantee that Eva's shell-exec surface can never be
    reached off the Mac. Raises SystemExit on any non-loopback host so a
    mis-config fails closed (the service does not start) rather than open.
    """
    h = (host or "").strip()
    if h in LOOPBACK_HOSTS:
        return
    try:
        if ipaddress.ip_address(h).is_loopback:
            return
    except ValueError:
        pass
    raise SystemExit(
        f"REFUSING TO BIND local-exec to '{host}': localhost-only (127.0.0.1). "
        f"This service must never be exposed off the Mac / via a tunnel."
    )


app = FastAPI(
    title="EVA Local-Exec",
    description=(
        "Localhost-only 'Mac hands' exec service. Allowlisted safe ops auto-run; "
        "everything else is gated behind one-tap Slack approval. Secret-masked "
        "and fully audited. Binds 127.0.0.1 only — never exposed via a tunnel."
    ),
    version=AGENT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExecRequest(BaseModel):
    command: str
    args: list[str] | None = None
    cwd: str | None = None
    triggered_by: str | None = "eva"
    timeout: int | None = None


class ApproveRequest(BaseModel):
    run_id: str
    approved: bool = True


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-local-exec",
        "version": AGENT_VERSION,
        "port": PORT,
        "bind": "127.0.0.1",
        "offline": service.offline,
        "allowlist_count": len(service.allowlist),
    }


@app.post("/local-exec/exec", tags=["Local-Exec"])
async def local_exec_exec(body: ExecRequest):
    """Run a command: allowlisted → runs now; otherwise → one-tap approval gate."""
    return service.exec_command(
        body.command, args=body.args, cwd=body.cwd,
        triggered_by=body.triggered_by or "eva", timeout=body.timeout)


@app.get("/local-exec/status", tags=["Local-Exec"])
async def local_exec_status():
    """Service health + allowlist summary + run counts by status."""
    return service.status()


@app.get("/local-exec/history", tags=["Local-Exec"])
async def local_exec_history(limit: int = 20):
    """Recent audited runs, newest first (capped)."""
    return service.history(limit=limit)


@app.post("/local-exec/approve", tags=["Local-Exec"])
async def local_exec_approve(body: ApproveRequest):
    """Approve/deny a pending non-allowlisted run (one-tap gate)."""
    return service.approve(body.run_id, approved=body.approved)


@app.post("/local-exec/approve/{run_id}", tags=["Local-Exec"])
async def local_exec_approve_link(run_id: str, approved: bool = True):
    """Approval link target (the URL posted to Slack)."""
    return service.approve(run_id, approved=approved)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Local-Exec 'Mac hands' service")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host to bind (loopback only; 0.0.0.0 is refused)")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    assert_localhost_bind(args.host)  # fail closed if not loopback
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
