"""
EVA Social-Scheduler — FastAPI microservice
============================================
Port: 8787

Native daily LinkedIn + X publisher for the eva-acquisition pipeline. Runs 5
posts/day at fixed America/New_York slots (08:00, 11:00, 14:00, 15:00, 17:00),
each gated through the existing social-publish Slack approve-per-post flow, then
LIKEs + comments the CTA and logs everything to Eva's own local sqlite store.

Endpoints:
  GET  /health              Health + slots + offline flag
  GET  /schedule            The content queue + fixed ET slot schedule
  POST /schedule/seed       Pre-seed the day-1 content queue (deduped)
  POST /schedule/run        One scheduler pass (submit due → publish approved)
  POST /schedule/sync       Sync engagement metrics into the unified store
  GET  /analytics           Latest engagement snapshot per post + totals

Offline-safe: with ``EVA_SOCIAL_SCHEDULER_OFFLINE=1`` (default in the sandbox)
the gate/engagement/state/analytics seams use no-op stubs and fire nothing real.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import scheduler
from loop import SchedulerLoop, next_slot_datetime
from service import SocialSchedulerService

AGENT_VERSION = "0.1.0"
PORT = 8787

service = SocialSchedulerService()
# Self-fire loop: computes the next ET slot, sleeps, then runs one pass. Started
# on FastAPI startup so it comes up with the launcher SERVICES entry. No-ops when
# EVA_SOCIAL_SCHEDULER_OFFLINE=1 (sandbox default) — fires nothing real.
loop = SchedulerLoop(service)

app = FastAPI(
    title="EVA Social-Scheduler",
    description=(
        "Native daily LinkedIn + X publisher. 5 posts/day on a fixed "
        "America/New_York schedule, each gated through the social-publish "
        "Slack approve-per-post flow, then LIKE + CTA comment/reply, with all "
        "content, post history, and engagement analytics in Eva's own local "
        "sqlite store."
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
    scheduled_date: Optional[str] = None


@app.on_event("startup")
async def _start_loop():
    """Start the self-fire loop unless disabled. No-op when offline."""
    if os.environ.get("EVA_SOCIAL_SCHEDULER_NO_LOOP") == "1":
        return
    loop.start()


@app.on_event("shutdown")
async def _stop_loop():
    loop.stop()


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-social-scheduler",
        "version": AGENT_VERSION,
        "port": PORT,
        "db": service.db_path,
        "offline": service.offline,
        "timezone": "America/New_York",
        "slots": scheduler.SLOTS,
        "loop_running": loop.is_running(),
        "next_slot_et": None if service.offline else next_slot_datetime().isoformat(),
    }


@app.get("/schedule", tags=["Schedule"])
async def get_schedule():
    """The content queue grouped by status + the fixed ET slot schedule."""
    return service.schedule()


@app.post("/schedule/seed", tags=["Schedule"])
async def seed_schedule(body: SeedIn | None = None):
    """Pre-seed the day-1 content queue (idempotent, deduped by headline)."""
    return service.seed(scheduled_date=(body.scheduled_date if body else None))


@app.post("/schedule/run", tags=["Schedule"])
async def run_schedule():
    """One scheduler pass: submit due posts, publish approved ones, prune."""
    return service.run()


@app.post("/schedule/sync", tags=["Analytics"])
async def sync_analytics(window_days: int = 30):
    """Pull current engagement metrics into the unified local analytics store."""
    return service.sync_analytics(window_days=window_days)


@app.get("/analytics", tags=["Analytics"])
async def get_analytics():
    """Latest engagement snapshot per (platform, post) + totals."""
    return service.analytics()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Social-Scheduler")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
