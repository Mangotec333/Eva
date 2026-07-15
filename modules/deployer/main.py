"""
EVA Deployer — FastAPI microservice
====================================
Port: 8789

The CI/CD self-update agent. A background loop polls GitHub for new commits on
``main`` every 5 hours and, when the remote is ahead, fast-forwards the local
checkout and gracefully restarts only the Eva services whose module code
changed — **fast-forward only, gated on no in-flight work, resilient, never
breaks a running Eva.**

Scope is Eva-repo self-update only (git pull + restart changed Eva services).
The eva-landing / Vercel deploy is handled separately by native Vercel
auto-deploy and is intentionally out of scope here.

Endpoints:
  GET  /health            Health + local SHA + poll interval + offline flag
  GET  /deployer/status   Current SHA, last check, last result
  POST /deployer/check    Manually trigger one poll → safe self-deploy pass
  GET  /deployer/history  Recent deploy passes (newest first)

Offline-safe: with ``EVA_DEPLOYER_OFFLINE=1`` (default in the sandbox) the git /
launcher / gate seams are not built and a check is a pure no-op — nothing is
pulled, nothing is restarted.
"""

from __future__ import annotations

import argparse
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import deployer as dep
from loop import DeployerLoop
from service import DeployerService

AGENT_VERSION = "0.1.0"
PORT = 8789

service = DeployerService()
# Self-poll loop: sleeps the interval, then runs one check() pass. Started on
# FastAPI startup so it comes up with the launcher SERVICES entry. No-ops when
# EVA_DEPLOYER_OFFLINE=1 (sandbox default) — polls/pulls/restarts nothing real.
loop = DeployerLoop(service)

app = FastAPI(
    title="EVA Deployer",
    description=(
        "CI/CD self-update agent. Polls GitHub for new commits on main every 5 "
        "hours and safely self-deploys: fast-forward-only pull, restart only the "
        "changed Eva services, gated on no in-flight work, resilient, never "
        "breaks a running Eva."
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


@app.on_event("startup")
async def _start_loop():
    """Start the self-poll loop unless disabled. No-op when offline."""
    if os.environ.get("EVA_DEPLOYER_NO_LOOP") == "1":
        return
    loop.start()


@app.on_event("shutdown")
async def _stop_loop():
    loop.stop()


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-deployer",
        "version": AGENT_VERSION,
        "port": PORT,
        "offline": service.offline,
        "repo": dep.REPO,
        "branch": dep.BRANCH,
        "poll_interval_seconds": dep.poll_interval_seconds(),
        "loop_running": loop.is_running(),
    }


@app.get("/deployer/status", tags=["Deployer"])
async def deployer_status():
    """Current local SHA, last check time, and last deploy result."""
    return service.status()


@app.post("/deployer/check", tags=["Deployer"])
async def deployer_check():
    """Manually trigger one poll → safe self-deploy pass (same as the loop tick)."""
    return service.check()


@app.get("/deployer/history", tags=["Deployer"])
async def deployer_history(limit: int = 20):
    """Recent deploy passes, newest first."""
    return service.history(limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Deployer CI/CD self-update agent")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
