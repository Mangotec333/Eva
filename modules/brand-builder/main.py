"""
EVA Brand-Builder — FastAPI microservice
========================================
Port: 8792

The Brand Builder is Eva's brand strategy/orchestration layer. It sits ABOVE
content-engine (:8767, makes content) and social-scheduler (:8787, approves +
posts): it writes content BRIEFS and NEVER posts. Approval stays L1 — drafts
only, the user approves before anything goes out.

Endpoints:
  GET  /brand/status                Module status + pipelines/blueprints/stale
  GET  /brand/pipelines             All strategy pipelines
  GET  /brand/pipelines/{id}        One pipeline
  GET  /brand/blueprints/{category} One market blueprint (by category slug or name)
  POST /brand/seed                  Seed the first pipeline from the blueprint md
  POST /brand/plan                  Weekly content plan (list of briefs)
  GET  /brand/briefs                Pending/queued briefs
  POST /brand/queue                 Emit briefs to content-engine (brand_brief_created)
  POST /brand/refresh               Re-check blueprints for staleness

Offline-safe: with ``EVA_BRAND_OFFLINE=1`` (sandbox default) the eva-state emits
are stubbed and missing pipelines/blueprints fall back to mocked objects.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import store
from loop import RefreshLoop
from service import BrandBuilderService

AGENT_VERSION = "0.1.0"
PORT = 8792

service = BrandBuilderService()
loop = RefreshLoop(service)

app = FastAPI(
    title="EVA Brand-Builder",
    description=(
        "Brand strategy/orchestration layer. Sits above content-engine (:8767) "
        "and social-scheduler (:8787): writes content briefs, never posts. "
        "Approval stays L1 (drafts only, user approves before posting)."
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
    pipeline_id: Optional[str] = None
    md_path: Optional[str] = None


class PlanIn(BaseModel):
    pipeline_id: str
    timeframe: str = "week"
    start_date: Optional[str] = None


class QueueIn(BaseModel):
    brief_ids: Optional[list[str]] = None
    pipeline_id: Optional[str] = None


@app.on_event("startup")
async def _start_loop():
    if os.environ.get("EVA_BRAND_NO_LOOP") == "1":
        return
    loop.start()


@app.on_event("shutdown")
async def _stop_loop():
    loop.stop()


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-brand-builder",
        "version": AGENT_VERSION,
        "port": PORT,
        "offline": service.offline,
        "loop_running": loop.is_running(),
    }


@app.get("/brand/status", tags=["Brand"])
async def brand_status():
    return service.status()


@app.get("/brand/pipelines", tags=["Brand"])
async def brand_pipelines():
    return {"pipelines": service.list_pipelines()}


@app.get("/brand/pipelines/{pipeline_id}", tags=["Brand"])
async def brand_pipeline(pipeline_id: str):
    p = service.get_pipeline(pipeline_id)
    if p is None:
        return {"error": f"unknown pipeline: {pipeline_id}"}
    return p


@app.get("/brand/blueprints/{category}", tags=["Brand"])
async def brand_blueprint(category: str):
    b = service.get_blueprint(category)
    if b is None:
        return {"error": f"unknown blueprint: {category}"}
    return b


@app.post("/brand/seed", tags=["Brand"])
async def brand_seed(body: SeedIn | None = None):
    kwargs = {}
    if body and body.pipeline_id:
        kwargs["pipeline_id"] = body.pipeline_id
    if body and body.md_path:
        kwargs["md_path"] = body.md_path
    return service.seed(**kwargs)


@app.post("/brand/plan", tags=["Brand"])
async def brand_plan(body: PlanIn):
    return service.plan(pipeline_id=body.pipeline_id, timeframe=body.timeframe,
                        start_date=body.start_date)


@app.get("/brand/briefs", tags=["Brand"])
async def brand_briefs(status: str | None = None):
    return {"briefs": service.list_briefs(status=status)}


@app.post("/brand/queue", tags=["Brand"])
async def brand_queue(body: QueueIn | None = None):
    return service.queue(
        brief_ids=(body.brief_ids if body else None),
        pipeline_id=(body.pipeline_id if body else None))


@app.post("/brand/refresh", tags=["Brand"])
async def brand_refresh():
    return service.refresh()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Brand-Builder")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    parser.add_argument("--seed", action="store_true", help="Seed the first pipeline and exit")
    args = parser.parse_args()
    if args.seed:
        import json as _json
        print(_json.dumps(service.seed(), indent=2)[:2000])
    else:
        uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
