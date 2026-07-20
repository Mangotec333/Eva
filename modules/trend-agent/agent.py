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

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")


class TrendAgent:
    VERSION = "1.0.0"

    def __init__(self) -> None:
        memory.init_db()

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
        return result


def engine_version() -> str:
    return ENGINE_VERSION
