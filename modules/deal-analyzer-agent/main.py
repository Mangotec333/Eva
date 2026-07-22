"""
EVA Deal Analyzer Agent — FastAPI microservice
==============================================
Port: 8801  (deal-scout runs on 8766)

The first agentic-operating-model service. Wraps DealAnalyzerAgent behind HTTP.

Endpoints:
  POST /analyze        Accept a deal (+ optional enrichment), run the agent, return scores
  GET  /deal/{id}      Fetch a previously scored deal from agent memory
  GET  /directive      Return the current live directive (directive.md)
  GET  /health         Health check

Plus run_deal_pipeline(): a cron-ready stub that will pull from sourcing
(deal-scout / connectors) and run each candidate through the agent.
"""

from __future__ import annotations

import argparse
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import memory
from agent import DealAnalyzerAgent, DIRECTIVE_PATH
from models import AgentHealth, AnalyzeRequest, DealV7

SCORING_VERSION = "7.0.0"
AGENT_VERSION = DealAnalyzerAgent.VERSION

# Single long-lived agent instance (stateless per-request apart from shared memory.db).
agent = DealAnalyzerAgent()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_directive_version() -> str:
    """Read the directive version from the `version:` line in directive.md."""
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
    title="EVA Deal Analyzer Agent",
    description=(
        "First instance of Eva's agentic operating model: an autonomous LLM-loop "
        "microservice that scores acquisition deals with the v7 engine and learns over time."
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=AgentHealth, tags=["Meta"])
async def health_check():
    return AgentHealth(
        status="ok",
        module="eva-deal-analyzer-agent",
        version=AGENT_VERSION,
        scoring_version=SCORING_VERSION,
        db=memory.DB_PATH,
        directive_version=_current_directive_version(),
    )


@app.get("/directive", response_class=PlainTextResponse, tags=["Meta"])
async def get_directive():
    """Return the agent's current live directive (directive.md)."""
    try:
        with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="directive.md not found")


@app.post("/analyze", tags=["Agent"])
async def analyze(payload: AnalyzeRequest):
    """Run the agent loop on a deal (+ optional enrichment) and return v7 scores."""
    ts = _now()
    deal = DealV7(
        id=str(uuid.uuid4()),
        source=payload.source,
        listing_id=payload.listing_id,
        url=payload.url,
        name=payload.name,
        category=payload.category,
        monthly_net=payload.monthly_net,
        annual_multiple=payload.annual_multiple,
        asking_price=payload.asking_price,
        age_years=payload.age_years,
        notes=payload.notes,
        buy_vs_build_decision=payload.buy_vs_build_decision,
        ai_proof_score=payload.ai_proof_score or 0.0,
        discovered_at=ts,
        created_at=ts,
        updated_at=ts,
    )
    enrichment = payload.enrichment.to_kwargs() if payload.enrichment else None
    result = agent.run_deal(deal, enrichment)
    return result


@app.get("/deal/{deal_id}", tags=["Agent"])
async def get_deal(deal_id: str = Path(..., description="Deal UUID")):
    """Fetch a previously scored deal from the agent's memory."""
    stored = memory.get_deal(deal_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")
    return stored


# ---------------------------------------------------------------------------
# Cron-ready pipeline (stub)
# ---------------------------------------------------------------------------

def run_deal_pipeline() -> dict:
    """STUB: pull candidate deals from sourcing and score each through the agent.

    TODO(next-phase): connect to the deal-scout DB / external connectors, fetch
    fresh candidates, run agent.run_deal() per candidate, and surface a shortlist.
    Wired to cron (launchd plist) once sourcing connectors land.
    """
    return {
        "status": "stub",
        "scored": 0,
        "note": "run_deal_pipeline is a stub pending sourcing connectors.",
        "ran_at": _now(),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Deal Analyzer Agent microservice")
    parser.add_argument("--port", type=int, default=8801, help="Port to bind (default: 8801)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", default=False, help="Hot reload (dev)")
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
