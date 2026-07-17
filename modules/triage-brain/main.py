"""
EVA Diracatron — FastAPI microservice
=====================================
Port: 8784

Diracatron is the top-level autonomous triage brain: it reads eva-state +
activity + signals, ranks priorities, dispatches to downstream agents, and
logs every decision back to eva-state so Eva learns.

Endpoints:
  GET  /health          Health + open-queue count + offline flag
  GET  /triage/queue    The current ranked, still-open triage queue
  POST /triage/run      Run one triage pass (poll → rank → queue)
  POST /triage/dispatch Eva's dispatch brain: {goal} → LLM decides which lobes
                        to invoke → fires them → logs to eva-state. Also accepts
                        {item_id} to dispatch one already-queued item.
  POST /triage/digest   Nightly prioritized stack-rank of open doors
  GET  /triage/registry The data-driven agent registry (all lobes)
  GET  /triage/history  Recent dispatch decisions (audit trail)

Offline-safe: with ``EVA_DIRACATRON_OFFLINE=1`` (default in the sandbox), all
sources/dispatch/state writes use stubs and nothing real is fired.
"""

from __future__ import annotations

import argparse
import os

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import store
from service import DiracatronService

AGENT_VERSION = "0.1.0"
PORT = 8784

service = DiracatronService()


app = FastAPI(
    title="EVA Diracatron",
    description=(
        "Top-level autonomous triage brain. Reads eva-state + activity + "
        "signals, ranks priorities, dispatches to downstream agents, and logs "
        "every decision back to eva-state so Eva learns."
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


@app.get("/health", tags=["Meta"])
async def health_check():
    q = store.list_queue(status=store.STATUS_OPEN, path=service.db_path)
    return {
        "status": "ok",
        "module": "eva-diracatron",
        "version": AGENT_VERSION,
        "port": PORT,
        "db": service.db_path,
        "offline": os.environ.get("EVA_DIRACATRON_OFFLINE") == "1",
        "open_queue": len(q),
    }


@app.get("/triage/queue", tags=["Triage"])
async def triage_queue():
    """Current ranked, still-open triage queue (highest priority first)."""
    return service.queue()


@app.post("/triage/run", tags=["Triage"])
async def triage_run():
    """Run one triage pass: poll every source, rank, and upsert the queue."""
    return service.run_pass()


@app.post("/triage/dispatch", tags=["Triage"])
async def triage_dispatch(
    body: dict = Body(..., description="{goal} to run the dispatch brain, or {item_id}")
):
    """Eva's dispatch brain.

    * ``{"goal": "..."}`` — first-principles: the LLM decides which lobes to
      invoke, Diracatron fires them via the registry, collects results, and
      logs the decision + every outcome to eva-state.
    * ``{"item_id": "..."}`` — dispatch one already-queued item to its owner.
    """
    goal = (body.get("goal") or body.get("intent") or "").strip()
    if goal:
        return service.dispatch_goal(goal, context=body.get("context"))

    item_id = (body.get("item_id") or body.get("id") or "").strip()
    if not item_id:
        raise HTTPException(status_code=422, detail="goal or item_id is required")
    result = service.dispatch(item_id)
    if not result.get("ok") and result.get("error", "").endswith("not found"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/triage/digest", tags=["Triage"])
async def triage_digest(body: dict = Body(default={}, description="{top?, alert?}")):
    """Nightly prioritized stack-rank of open doors + market potential."""
    return service.digest(top=int(body.get("top", 10)),
                          alert=bool(body.get("alert", False)))


@app.get("/triage/registry", tags=["Triage"])
async def triage_registry():
    """The data-driven agent registry — every lobe Diracatron can orchestrate."""
    return {"count": len(service.registry.slugs()),
            "agents": service.registry.to_catalog()}


@app.get("/triage/history", tags=["Triage"])
async def triage_history(limit: int = 50):
    """Recent dispatch decisions (audit trail from dispatch_history)."""
    return {"items": service.history(limit=limit)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Diracatron triage brain")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
