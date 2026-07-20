"""
EVA Trend Agent — agent wrapper
=================================
Wraps the deterministic trend_engine with run persistence + directive read,
following the deal-financing-agent pattern (agent.py owns the loop, main.py
exposes it over HTTP).

Scoring math is deterministic (v1, no LLM call in the compute path). The
qualitative research that produces each sector's sub-scores (historical
resilience, AI disruption exposure, structural demand) is done upstream
(Perplexity research / EVA research subagent) and supplied as case JSON —
see cases/basic_needs_2026.json. This keeps the "prove me wrong" judgement
auditable: every score traces to cited sources, and the composite/verdict
math is never hand-tuned to fit a preferred conclusion.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from trend_engine import ENGINE_VERSION, run_thesis_model
from models import ThesisRunInput, ThesisRunResult

import memory
from state_client import StateLedgerClient, build_state_client

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")


class TrendAgent:
    VERSION = "1.0.0"

    def __init__(self, state_client: StateLedgerClient | None = None) -> None:
        memory.init_db()
        self.state_client = state_client or build_state_client()

    def run_thesis(self, inp: ThesisRunInput) -> ThesisRunResult:
        result = run_thesis_model(inp)
        run_id = str(uuid.uuid4())
        memory.save_run(
            run_id=run_id,
            thesis_statement=inp.thesis_statement,
            input_json=inp.model_dump_json(),
            result_json=result.model_dump_json(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._emit_run(run_id, inp, result)
        return result

    def _emit_run(self, run_id: str, inp: ThesisRunInput, result: ThesisRunResult) -> None:
        """Every run is logged (routine, not triaged). A REFUTED verdict is
        additionally emitted as ``thesis_refuted`` — Diracatron treats that as
        a near-alignment-flag-priority signal, since it means the macro
        footing under a whole strategy track may be wrong, not just one idea.
        """
        self.state_client.emit(
            event_type="thesis_run_completed",
            summary=f"Thesis run '{inp.thesis_statement[:80]}' -> {result.verdict}",
            entity_id=run_id,
            payload={
                "thesis_statement": inp.thesis_statement,
                "verdict": result.verdict,
                "verdict_confidence": result.verdict_confidence,
                "avg_durability_score": result.avg_durability_score,
            },
        )
        if result.verdict == "REFUTED":
            self.state_client.emit(
                event_type="thesis_refuted",
                summary=(f"REFUTED: '{inp.thesis_statement[:80]}' "
                         f"(avg durability {result.avg_durability_score}/10, "
                         f"confidence {result.verdict_confidence})"),
                entity_id=run_id,
                payload={
                    "thesis_statement": inp.thesis_statement,
                    "verdict": result.verdict,
                    "verdict_confidence": result.verdict_confidence,
                    "avg_durability_score": result.avg_durability_score,
                    "min_durability_score": result.min_durability_score,
                    "urgent": True,
                },
            )


def engine_version() -> str:
    return ENGINE_VERSION
