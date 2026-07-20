"""
EVA Idea-Generator-Agent — FastAPI microservice
================================================
Port: 8793

Scores new venture/product ideas against the goal (Storeys RE PE fund +
Mangotec AI-agency revenue) and against the existing portfolio, computes a
BUILD / PARTNER / WATCH / PASS recommendation, flags "acquire instead of
build" candidates, and raises devil's-advocate flags (unverified demand,
shiny-object drift, no counter-thesis). Also runs a daily system-wide
alignment/red-flag digest over eva-state activity.

Endpoints:
  GET  /idea/health         Module status
  POST /idea/score          Score one idea, persist + emit to eva-state
  GET  /idea/runs           Scored-idea history (optional ?idea_id=)
  POST /idea/alignment/run  Trigger the alignment digest now
  GET  /idea/alignment/history  Past digest runs (newest first)

Offline-safe: with ``EVA_IDEA_OFFLINE=1`` (sandbox default) the eva-state
client and Slack alert are stubbed/skipped — no network. Disable the daily
loop with ``EVA_IDEA_NO_LOOP=1``.
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from loop import AlignmentLoop
from models import IdeaInput
from service import IdeaGeneratorService

AGENT_VERSION = "0.1.0"
PORT = 8793

service = IdeaGeneratorService()
loop = AlignmentLoop(service)

app = FastAPI(
    title="EVA Idea-Generator-Agent",
    description=(
        "Scores new venture ideas against Eva's goal + existing portfolio, "
        "computes build/partner/watch/pass, and runs a daily alignment "
        "red-flag digest over eva-state activity."),
    version=AGENT_VERSION,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AlignmentRunRequest(BaseModel):
    window_days: int = 7


class ReviewRequest(BaseModel):
    """Diracatron's dispatch target for KIND_IDEA_SCORED / KIND_ALIGNMENT_FLAG.
    L1-autonomy ack only — this never auto-builds/auto-acquires anything, it
    just records that a human/EVA looked at the item."""
    kind: str = ""
    entity_id: str = ""
    note: str = ""


@app.on_event("startup")
def _startup() -> None:
    loop.start()


@app.get("/idea/health")
def health() -> dict:
    return {
        "ok": True,
        "agent": "idea-generator-agent",
        "version": AGENT_VERSION,
        "offline": service.offline,
        "loop_running": loop.is_running(),
    }


@app.post("/idea/score")
def score(idea: IdeaInput) -> dict:
    result = service.score_idea(idea)
    return result.model_dump()


@app.get("/idea/runs")
def runs(idea_id: Optional[str] = None, limit: Optional[int] = None) -> dict:
    return {"runs": service.list_idea_runs(idea_id=idea_id, limit=limit)}


@app.post("/idea/alignment/run")
def alignment_run(req: AlignmentRunRequest) -> dict:
    return service.run_alignment_check(window_days=req.window_days)


@app.get("/idea/alignment/history")
def alignment_history(limit: int = 30) -> dict:
    return {"digests": service.list_digests(limit=limit)}


@app.post("/idea/review")
def review(req: ReviewRequest) -> dict:
    """Diracatron dispatch target: acknowledge a queued idea-score or
    alignment-flag item was reviewed. Read-only side effect (eva-state emit
    only) — never files, builds, or acquires anything on its own."""
    try:
        service.state.emit(
            event_type="idea_item_reviewed",
            summary=f"Reviewed {req.kind or 'item'}: {req.note}"[:500],
            entity_id=req.entity_id,
            payload=req.model_dump(),
        )
    except Exception:
        pass
    return {"ok": True, "reviewed": req.entity_id or req.kind}


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA Idea-Generator-Agent")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
