"""
EVA Retro-Agent — FastAPI microservice
======================================
Port: 8795

The weekly retrospective lobe. Every Monday 8:00 AM PT (via launchd) it reviews
the prior 7 days and answers, deterministically, whether the week moved the
$10K/month critical path or just churned infrastructure — bucketing the week into
four lenses (shipped / revenue-pipeline movement / stale blockers / were last
week's course-correction priorities worked on) and rolling them into a goal-drift
status ladder: REVENUE_WIN > STALLED_BLOCKER > DRIFTING > ON_TRACK.

The digest is written to this module's own append-only ledger AND emitted back to
eva-state so Diracatron and every other lobe see it on the shared timeline.

Endpoints:
  GET  /health          Module status
  GET  /directive       This module's directive.md
  POST /retro/run       Run the weekly retro now (optional {"week_end": "YYYY-MM-DD"})
  GET  /retro/latest    The most recent digest
  GET  /retro/history   Past digests, newest first (?limit=)
  GET  /retro/{run_id}  One digest by run id

Offline-safe: with ``EVA_RETRO_OFFLINE=1`` the eva-state client, retro-log
source, and brain are stubbed — no network. The schedule is owned by launchd
(``launchd/com.eva.retro-agent.plist``); run one retro headless with
``python3 main.py --run-once``.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import memory
from service import RetroService

AGENT_VERSION = "0.1.0"
PORT = 8795

service = RetroService()

app = FastAPI(
    title="EVA Retro-Agent",
    description=(
        "Weekly $10K/month course-correction lobe: reviews the prior 7 days over "
        "eva-state, catches revenue-goal drift (infra churn outpacing revenue "
        "movement), flags stale blockers, and checks whether last week's stated "
        "course-correction priorities were actually worked on."),
    version=AGENT_VERSION,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    week_end: Optional[str] = None
    model_config = {"protected_namespaces": ()}


@app.on_event("startup")
def _startup() -> None:
    memory.init_db()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "agent": "retro-agent",
        "version": AGENT_VERSION,
        "offline": service.offline,
        "port": PORT,
    }


@app.get("/directive")
def directive() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "directive.md")
    try:
        with open(path, "r") as f:
            return {"directive": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/retro/run")
def run(req: RunRequest) -> dict:
    return service.run_retro(week_end=req.week_end)


@app.get("/retro/latest")
def latest() -> dict:
    digest = service.latest()
    if not digest:
        raise HTTPException(status_code=404, detail="no retro digest yet")
    return digest


@app.get("/retro/history")
def history(limit: int = 30) -> dict:
    return {"digests": service.history(limit=limit)}


@app.get("/retro/{run_id}")
def by_id(run_id: str) -> dict:
    digest = service.get(run_id)
    if not digest:
        raise HTTPException(status_code=404, detail=f"no retro digest for {run_id}")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Retro-Agent")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one weekly retro headless (for launchd) and exit.")
    parser.add_argument("--week-end", default=None,
                        help="Override the retro window end date (YYYY-MM-DD).")
    args = parser.parse_args()

    if args.run_once:
        result = service.run_retro(week_end=args.week_end)
        print(result.get("narrative") or result.get("status", ""))
        return

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
