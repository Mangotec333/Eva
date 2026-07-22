"""
EVA Trend Agent — FastAPI microservice
========================================
Port: 8788

Macro-thesis stress-test engine: sourced sector sub-scores (historical
resilience, AI disruption exposure, structural demand) -> weighted durability
score -> ranked scorecard -> verdict (SUPPORTED / PARTIALLY_SUPPORTED / REFUTED).

Endpoints:
  POST /model         Run the thesis model on a set of sector assessments
  GET  /run/{id}       Fetch a previously computed run
  GET  /runs           List runs
  GET  /directive      Return the current live directive (directive.md)
  GET  /health         Health check
"""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from agent import TrendAgent, DIRECTIVE_PATH
from models import AgentHealth, ThesisRunInput, ThesisRunResult
from app_models import AppScanRunInput, AppScanRunResult

agent = TrendAgent()


def _current_directive_version() -> str:
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
    memory.init_db()
    yield


app = FastAPI(
    title="EVA Trend Agent",
    description="Macro-thesis stress-test engine: sector sub-scores -> weighted durability score -> verdict.",
    version=TrendAgent.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=AgentHealth, tags=["Meta"])
async def health_check():
    return AgentHealth(
        status="ok",
        module="eva-trend-agent",
        version=TrendAgent.VERSION,
        directive_version=_current_directive_version(),
    )


@app.get("/directive", response_class=PlainTextResponse, tags=["Meta"])
async def get_directive():
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/model", response_model=ThesisRunResult, tags=["Agent"])
async def run_model(payload: ThesisRunInput):
    """Run the thesis stress-test model on sourced sector assessments and return the scorecard + verdict."""
    return agent.run_thesis(payload)


@app.get("/runs", tags=["Agent"])
async def list_runs():
    return memory.list_runs()


@app.get("/run/{run_id}", tags=["Agent"])
async def get_run(run_id: str = Path(..., description="Run UUID")):
    stored = memory.get_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return stored


@app.post("/app-scan", response_model=AppScanRunResult, tags=["App Scan"])
async def run_app_scan(payload: AppScanRunInput):
    """Run the App Category Scan: aggregate top-10-per-category research into
    an opportunity-tiered, second-look report for short-term revenue."""
    return agent.run_app_scan(payload)


@app.get("/app-scan/runs", tags=["App Scan"])
async def list_app_scan_runs():
    return memory.list_app_scan_runs()


@app.get("/app-scan/run/{run_id}", tags=["App Scan"])
async def get_app_scan_run(run_id: str = Path(..., description="Run UUID")):
    stored = memory.get_app_scan_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"App scan run {run_id!r} not found")
    return stored


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Trend Agent microservice")
    parser.add_argument("--port", type=int, default=8788, help="Port to bind (default: 8788)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", default=False, help="Hot reload (dev)")
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
