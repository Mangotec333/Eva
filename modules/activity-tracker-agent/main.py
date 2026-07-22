"""
EVA Activity-Tracker-Agent — FastAPI microservice
==================================================
Port: 8794

Logs and monitors all EVA activity across every lobe (via eva-state), buckets
today's events by project, catches recurring patterns (blockers, stalled
threads, high-effort/zero-revenue drift), and flags any revenue traction so
time and resources get reallocated there first. Runs once per day (EOD) and
keeps a digest history for course-correction the following day.

Endpoints:
  GET  /health              Module status
  GET  /directive           This module's directive.md
  POST /activity/run        Trigger today's digest now (optional {"date": "YYYY-MM-DD"})
  GET  /activity/today      Today's digest (runs it if not already run)
  GET  /activity/history    Past digest runs, newest first (?limit=)
  GET  /activity/{date}     One day's digest by date (YYYY-MM-DD)
  POST /activity/review     Diracatron dispatch target — ack a queued item

Offline-safe: with ``EVA_ACTIVITY_OFFLINE=1`` (sandbox default) the
eva-state client and Slack alert are stubbed/skipped — no network. Disable
the daily loop with ``EVA_ACTIVITY_NO_LOOP=1``.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from loop import DailyDigestLoop
from service import ActivityTrackerService

AGENT_VERSION = "0.1.0"
PORT = 8794

service = ActivityTrackerService()
loop = DailyDigestLoop(service)

app = FastAPI(
    title="EVA Activity-Tracker-Agent",
    description=(
        "Daily activity logger + pattern catcher over eva-state: buckets "
        "effort by project, flags recurring blockers and high-activity/"
        "zero-revenue drift, and surfaces revenue traction to double down on."),
    version=AGENT_VERSION,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    date: Optional[str] = None


class ReviewRequest(BaseModel):
    """Diracatron's dispatch target for KIND_ACTIVITY_DIGEST /
    KIND_REVENUE_TRACTION. L1-autonomy ack only — records that a human/EVA
    looked at the item, never auto-reallocates anything on its own."""
    kind: str = ""
    entity_id: str = ""
    note: str = ""


@app.on_event("startup")
def _startup() -> None:
    loop.start()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "agent": "activity-tracker-agent",
        "version": AGENT_VERSION,
        "offline": service.offline,
        "loop_running": loop.is_running(),
    }


@app.get("/directive")
def directive() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "directive.md")
    try:
        with open(path, "r") as f:
            return {"directive": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/activity/run")
def run(req: RunRequest) -> dict:
    return service.run_daily_digest(date=req.date)


@app.get("/activity/today")
def today() -> dict:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = service.get_digest(today_str)
    if existing:
        return existing
    return service.run_daily_digest(date=today_str)


@app.get("/activity/history")
def history(limit: int = 30) -> dict:
    return {"digests": service.list_digests(limit=limit)}


@app.get("/activity/{date}")
def by_date(date: str) -> dict:
    digest = service.get_digest(date)
    if not digest:
        raise HTTPException(status_code=404, detail=f"no digest for {date}")
    return digest


@app.post("/activity/review")
def review(req: ReviewRequest) -> dict:
    """Diracatron dispatch target: acknowledge a queued activity-digest or
    revenue-traction item was reviewed. Read-only side effect (eva-state
    emit only) — never reallocates, hires, or spends on its own."""
    try:
        service.state.emit(
            event_type="activity_item_reviewed",
            summary=f"Reviewed {req.kind or 'item'}: {req.note}"[:500],
            entity_id=req.entity_id,
            payload=req.model_dump(),
        )
    except Exception:
        pass
    return {"ok": True, "reviewed": req.entity_id or req.kind}


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Activity-Tracker-Agent")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
