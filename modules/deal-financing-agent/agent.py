"""
EVA Deal Financing Agent — agent wrapper
==========================================
Wraps the deterministic financing_engine with run persistence + directive
read, following the deal-analyzer-agent pattern (agent.py owns the loop,
main.py exposes it over HTTP).

The deterministic engine (financing_engine.py) is the authoritative core.
This wrapper adds no LLM call in v1 — bottoms-up financial modeling does not
need qualitative judgement to be correct, only correct arithmetic. An LLM
narrative/rationale layer can be added later without touching the engine.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from financing_engine import ENGINE_VERSION, run_financing_model
from models import DealFinancingInput, DealFinancingResult

import memory

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")


class DealFinancingAgent:
    VERSION = "1.0.0"

    def __init__(self) -> None:
        memory.init_db()

    def run_deal(self, inp: DealFinancingInput) -> DealFinancingResult:
        result = run_financing_model(inp)
        run_id = str(uuid.uuid4())
        memory.save_run(
            run_id=run_id,
            deal_name=inp.deal_name,
            input_json=inp.model_dump_json(),
            result_json=result.model_dump_json(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return result


def engine_version() -> str:
    return ENGINE_VERSION
