"""
EVA Deal Financing Agent — FastAPI microservice
================================================
Port: 8786

Bottoms-up acquisition financing model: revenue/opex -> NOI -> amortized debt
service -> cash flow to equity -> DSCR / cash-on-cash / equity multiple / IRR.

Endpoints:
  POST /model         Run the financing model on a deal input, return full result
  GET  /run/{id}       Fetch a previously computed run
  GET  /runs           List runs (optional ?deal_name= filter)
  GET  /directive      Return the current live directive (directive.md)
  GET  /health         Health check
"""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from agent import DealFinancingAgent, DIRECTIVE_PATH
from models import AgentHealth, DealFinancingInput, DealFinancingResult

agent = DealFinancingAgent()


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
    title="EVA Deal Financing Agent",
    description="Bottoms-up acquisition financing model: NOI -> debt service -> cash flow -> returns.",
    version=DealFinancingAgent.VERSION,
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
        module="eva-deal-financing-agent",
        version=DealFinancingAgent.VERSION,
        directive_version=_current_directive_version(),
    )


@app.get("/directive", response_class=PlainTextResponse, tags=["Meta"])
async def get_directive():
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/model", response_model=DealFinancingResult, tags=["Agent"])
async def run_model(payload: DealFinancingInput):
    """Run the bottoms-up financing model on a deal and return full results."""
    return agent.run_deal(payload)


@app.get("/runs", tags=["Agent"])
async def list_runs(deal_name: str | None = Query(default=None)):
    return memory.list_runs(deal_name)


@app.get("/run/{run_id}", tags=["Agent"])
async def get_run(run_id: str = Path(..., description="Run UUID")):
    stored = memory.get_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return stored


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Deal Financing Agent microservice")
    parser.add_argument("--port", type=int, default=8786, help="Port to bind (default: 8786)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", default=False, help="Hot reload (dev)")
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
