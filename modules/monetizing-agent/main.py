"""
EVA Monetizing Agent — FastAPI microservice
============================================
Port: 8772

The governed successor to the Yaksha cron prototype
(``modules/angels/angel3_monetization/``). Runs the weekly revenue-leak scan
(Mine -> Match -> Package -> Route -> Follow-up), produces the very-brief-pithy
Sunday brief as the approval gate, and only executes plays once a brief is
approved.

Endpoints:
  GET  /health              Health + last-run summary
  GET  /directive           Current live directive (directive.md)
  POST /scan                Run the weekly revenue-leak scan (returns the brief)
  GET  /brief/latest        Most recent Sunday brief (+ its plays)
  GET  /brief/{id}          A specific brief
  POST /brief/{id}/approve  APPROVAL GATE — flip the brief's plays to approved
  POST /brief/{id}/execute  Execute approved plays (gated; Stub transport offline)
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from service import MonetizingService, NotFoundError

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")
AGENT_VERSION = "0.1.0"

service = MonetizingService()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _directive_version() -> str:
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip().lower().startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass
    return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory.init_db(service.db_path)
    yield


app = FastAPI(
    title="EVA Monetizing Agent",
    description=(
        "Weekly revenue-leak detector. Mines all activity, ranks under-monetized "
        "signals by cash proximity, packages the top plays into approval-gated "
        "next-week actions, and learns from what converts."
    ),
    version=AGENT_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Meta"])
async def health_check():
    run = memory.latest_run(service.db_path)
    brief = memory.latest_brief(service.db_path)
    return {
        "status": "ok",
        "module": "eva-monetizing-agent",
        "version": AGENT_VERSION,
        "port": 8772,
        "db": service.db_path,
        "directive_version": _directive_version(),
        "last_run": {
            "at": run["timestamp"] if run else None,
            "outputs": run["outputs"] if run else None,
        },
        "latest_brief": {
            "id": brief["id"] if brief else None,
            "week_of": brief["week_of"] if brief else None,
            "status": brief["status"] if brief else None,
            "est_cash": brief["est_cash"] if brief else None,
        },
    }


@app.get("/directive", response_class=PlainTextResponse, tags=["Meta"])
async def get_directive():
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/scan", tags=["Agent"])
async def scan():
    """Run the weekly revenue-leak scan and return the pending-approval brief."""
    return service.scan()


@app.get("/brief/latest", tags=["Brief"])
async def brief_latest():
    brief = service.latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="no briefs yet — run POST /scan")
    return brief


@app.get("/brief/{brief_id}", tags=["Brief"])
async def brief_get(brief_id: str = Path(..., description="Brief UUID")):
    try:
        return service.get_brief(brief_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/brief/{brief_id}/approve", tags=["Brief"])
async def brief_approve(brief_id: str = Path(..., description="Brief UUID")):
    """APPROVAL GATE: flip the brief's plays to approved-for-execution."""
    try:
        return service.approve(brief_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/brief/{brief_id}/execute", tags=["Brief"])
async def brief_execute(brief_id: str = Path(..., description="Brief UUID")):
    """Execute the APPROVED plays of a brief (gated; refuses unapproved plays)."""
    try:
        return service.execute(brief_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Monetizing Agent microservice")
    parser.add_argument("--port", type=int, default=8772, help="Port to bind (default: 8772)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
