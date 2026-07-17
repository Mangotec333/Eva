"""
EVA Health Monitor — FastAPI microservice
=========================================
Port: 8788  (context-api 8765 … brand-builder 8792; this fills the free 8788)

Cross-module watchdog: polls every monitored module's /health endpoint on a
tick, records up/down/latency to its own SQLite, and raises an alert when a
module stays down for N consecutive ticks. All network I/O is behind a
HealthClient Protocol with an offline stub, so the module is fully testable
without any live services.

Endpoints:
  GET    /health           This monitor's own health + last-run summary
  POST   /tick             Probe all modules, record, raise/resolve alerts
  GET    /status           Latest status per monitored module
  GET    /modules          The monitored-module config list
  GET    /checks           Recent raw health-check rows (?module=&limit=)
  GET    /alerts           Alerts (?status=open|resolved)
  GET    /ledger           Append-only event ledger
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import database as db
from config import HEALTH_MONITOR_PORT
from models import HealthResponse, TickRequest
from service import HealthMonitorService, NotFoundError

VERSION = "1.0.0"

service = HealthMonitorService()

app = FastAPI(
    title="EVA Health Monitor",
    description=(
        "Cross-module /health watchdog with consecutive-failure alerting and an "
        "append-only ledger. Offline-testable via a HealthClient stub."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn):
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    return HealthResponse(
        status="ok",
        module="eva-health-monitor",
        version=VERSION,
        db=db.DB_PATH,
        client=service.client.name,
        monitored=len(service.targets),
        failure_threshold=service.failure_threshold,
        last_run=service.last_run(),
    )


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

@app.post("/tick", tags=["Monitor"])
def tick(payload: TickRequest = TickRequest()):
    return _handle(lambda: service.tick(actor=payload.actor))


@app.get("/status", tags=["Monitor"])
def status():
    rows = service.status()
    return {"status": rows, "count": len(rows)}


@app.get("/modules", tags=["Monitor"])
def modules():
    rows = service.list_targets()
    return {"modules": rows, "count": len(rows)}


@app.get("/checks", tags=["Monitor"])
def checks(
    module: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    rows = service.recent_checks(module=module, limit=limit)
    return {"checks": rows, "count": len(rows)}


@app.get("/alerts", tags=["Monitor"])
def alerts(status: Optional[str] = Query(default=None)):
    rows = service.list_alerts(status=status)
    return {"alerts": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@app.get("/ledger", tags=["Ledger"])
def query_ledger(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
):
    rows = service.query_ledger(from_ts=from_, to_ts=to, event_type=event_type)
    return {"ledger": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Health Monitor microservice")
    parser.add_argument("--port", type=int, default=HEALTH_MONITOR_PORT,
                        help=f"Port (default: {HEALTH_MONITOR_PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
