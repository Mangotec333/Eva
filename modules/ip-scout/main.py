"""
EVA IP-Scout — FastAPI microservice
===================================
Port: 8791

IP-Scout / Prior-Art Triage is Eva's **L1-autonomy** invention-triage lobe. It
runs a daily incremental novelty/prior-art triage over invention-idea seeds
(user-seeded ``~/.eva/ip_ideas.json`` + Eva-activity mining) and surfaces what's
worth a **patent attorney's review**. It NEVER files, submits, or asserts
patentability.

Endpoints:
  GET  /ip/status          Module status + sensors + last run + reports
  GET  /ip/ideas           All idea seeds (optional ?status=pending|triaged)
  GET  /ip/idea/{id}       One idea + its latest disclosure
  POST /ip/seed            Add an invention idea seed
  POST /ip/scan            Trigger a triage run over pending ideas
  GET  /ip/history         Past triage runs (newest first)
  GET  /ip/report/{date}   The daily markdown report for a date (YYYY-MM-DD)

Offline-safe: with ``EVA_IP_OFFLINE=1`` (sandbox default) the prior-art provider
and eva-state emits are mocked/stubbed — no network. Disable the loop with
``EVA_IP_NO_LOOP=1``.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from loop import TriageLoop
from service import IPScoutService

AGENT_VERSION = "0.1.0"
PORT = 8791

service = IPScoutService()
loop = TriageLoop(service)

app = FastAPI(
    title="EVA IP-Scout",
    description=(
        "L1-autonomy prior-art triage. Daily incremental novelty/prior-art "
        "triage over invention-idea seeds; surfaces what's worth a patent "
        "attorney's review. Never files or asserts patentability."
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


class SeedIn(BaseModel):
    title: str
    description: str = ""
    category: str = "uncategorized"
    idea_id: Optional[str] = None


class ScanIn(BaseModel):
    report_date: Optional[str] = None
    mine: bool = True


@app.on_event("startup")
async def _start_loop():
    if os.environ.get("EVA_IP_NO_LOOP") == "1":
        return
    loop.start()


@app.on_event("shutdown")
async def _stop_loop():
    loop.stop()


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-ip-scout",
        "version": AGENT_VERSION,
        "port": PORT,
        "offline": service.offline,
        "provider": service.provider.name,
        "loop_running": loop.is_running(),
    }


@app.get("/ip/status", tags=["IP"])
async def ip_status():
    return service.status()


@app.get("/ip/ideas", tags=["IP"])
async def ip_ideas(status: Optional[str] = None):
    return {"ideas": service.list_ideas(status=status)}


@app.get("/ip/idea/{idea_id}", tags=["IP"])
async def ip_idea(idea_id: str):
    idea = service.get_idea(idea_id)
    if idea is None:
        return {"error": f"unknown idea: {idea_id}"}
    return idea


@app.post("/ip/seed", tags=["IP"])
async def ip_seed(body: SeedIn):
    return service.seed_idea(
        title=body.title, description=body.description,
        category=body.category, idea_id=body.idea_id)


@app.post("/ip/scan", tags=["IP"])
async def ip_scan(body: ScanIn | None = None):
    return service.scan(
        report_date=(body.report_date if body else None),
        mine=(body.mine if body else True))


@app.get("/ip/history", tags=["IP"])
async def ip_history(limit: Optional[int] = None):
    return {"runs": service.history(limit=limit)}


@app.get("/ip/report/{report_date}", response_class=PlainTextResponse, tags=["IP"])
async def ip_report(report_date: str):
    md = service.get_report(report_date)
    if md is None:
        return PlainTextResponse(f"No report for {report_date}", status_code=404)
    return md


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA IP-Scout")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    parser.add_argument("--scan", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()
    if args.scan:
        import json as _json
        res = service.scan()
        res.pop("disclosures", None)
        print(_json.dumps(res, indent=2)[:2000])
    else:
        uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
