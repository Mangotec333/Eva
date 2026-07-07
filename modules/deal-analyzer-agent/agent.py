"""
EVA Deal Analyzer Agent — autonomous LLM-loop scaffold
======================================================

This is the FIRST instance of Eva's new agentic operating model: every task
becomes an autonomous LLM-loop microservice agent that learns over time.

THE LOOP:  observe() -> reason() -> act() -> learn()

  observe()  gather the deal + any enrichment into a structured context
  reason()   score the deal. The DETERMINISTIC core (scoring_v7.analyze_deal_v7)
             is authoritative today; an LLM hook is stubbed for the next phase to
             add qualitative judgement / enrichment synthesis ON TOP of the core.
  act()      persist the scored deal + the run to memory.db
  learn()    (stub) ingest deal outcomes (passed/LOI/closed) to recalibrate
             weights and evolve the live directive

SEPARATION OF CONCERNS (important): the v7 scoring engine is pure and fully
testable without an LLM. The LLM is an ADDITIVE reasoning layer, never a
dependency of the numeric core. If the LLM hook is never wired, the agent still
produces complete, deterministic scores.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import memory
from models import DealV7
from scoring_v7 import analyze_deal_v7

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")


# ===========================================================================
# LLM HOOK — STUBBED FOR NEXT PHASE
# ===========================================================================

# TODO(next-phase): wire a live LLM call here. Expected interface:
#
#     def llm_call(prompt: str, context: dict) -> dict:
#         '''Send `prompt` + `context` to the model, return STRUCTURED JSON.
#         Expected return shape:
#             {
#               "qualitative_notes": str,      # narrative judgement on the deal
#               "enrichment_suggestions": {    # fields the agent should go source
#                   "tam_usd": float | None,
#                   "named_competitors": [str],
#                   ...
#               },
#               "confidence": float,           # 0-1 self-assessed confidence
#               "tokens": int                  # tokens consumed (for agent_runs)
#             }
#         Must be side-effect free w.r.t. scoring — the numeric core stays
#         authoritative. The LLM output is advisory / enrichment only.
#         '''
#
# For now `reason()` runs WITHOUT the LLM and records tokens=0.
LLMCallable = Callable[[str, dict], dict]


def _null_llm(prompt: str, context: dict) -> dict:
    """Placeholder LLM hook. Returns an empty, zero-token advisory payload."""
    return {
        "qualitative_notes": "",
        "enrichment_suggestions": {},
        "confidence": 0.0,
        "tokens": 0,
        "_stub": True,
    }


def build_reasoning_prompt(deal: DealV7, enrichment: Optional[dict], directive: str) -> str:
    """Construct the prompt the LLM hook will receive (used once the hook is live)."""
    return (
        "You are the EVA Deal Analyzer Agent. Live directive:\n"
        f"{directive}\n\n"
        "A deterministic v7 scoring engine has already produced numeric scores. "
        "Provide qualitative judgement and flag enrichment gaps. Do NOT restate the numbers.\n\n"
        f"DEAL: {deal.name} ({deal.category} -> {deal.category_v2}), "
        f"${deal.monthly_net:,.0f}/mo, {deal.annual_multiple:g}x, {deal.age_years:g}yr.\n"
        f"ENRICHMENT PRESENT: {sorted((enrichment or {}).keys())}\n"
    )


# ===========================================================================
# THE AGENT
# ===========================================================================

class DealAnalyzerAgent:
    """Autonomous observe -> reason -> act -> learn loop for deal scoring."""

    VERSION = "0.1.0"

    def __init__(
        self,
        llm_call: Optional[LLMCallable] = None,
        db_path: str = memory.DB_PATH,
    ):
        # llm_call defaults to the null stub — the agent is fully functional without an LLM.
        self.llm_call: LLMCallable = llm_call or _null_llm
        self.db_path = db_path
        memory.init_db(self.db_path)

    # -- directive -----------------------------------------------------------

    def load_directive(self) -> str:
        """Read the current live directive (falls back to empty string)."""
        try:
            with open(DIRECTIVE_PATH, "r", encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    # -- observe -------------------------------------------------------------

    def observe(self, deal: DealV7, enrichment: Optional[dict] = None) -> dict:
        """Assemble the structured context for a reasoning pass."""
        return {
            "deal": deal.model_dump(),
            "enrichment": dict(enrichment or {}),
            "directive": self.load_directive(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    # -- reason --------------------------------------------------------------

    def reason(self, context: dict) -> dict:
        """Score the deal.

        The deterministic v7 engine is authoritative. The LLM hook (stubbed) runs
        alongside to add advisory qualitative notes + enrichment suggestions.
        """
        deal = DealV7(**context["deal"])
        enrichment = context.get("enrichment") or {}

        # 1) Deterministic core — always runs, no network/LLM.
        scored = analyze_deal_v7(deal, enrichment=enrichment or None)

        # 2) Advisory LLM layer — stubbed today (tokens=0).
        prompt = build_reasoning_prompt(scored, enrichment, context.get("directive", ""))
        advisory = self.llm_call(prompt, context)

        return {
            "scored_deal": scored.model_dump(),
            "advisory": advisory,
            "tokens": int(advisory.get("tokens", 0)),
        }

    # -- act -----------------------------------------------------------------

    def act(self, context: dict, reasoning: dict) -> dict:
        """Persist the scored deal and the run to memory."""
        scored = reasoning["scored_deal"]
        memory.save_deal(scored, path=self.db_path)
        run_id = memory.save_run(
            deal_id=scored.get("id", ""),
            inputs={"deal": context["deal"], "enrichment": context.get("enrichment", {})},
            outputs={
                "overall_score": scored.get("overall_score"),
                "category_v2": scored.get("category_v2"),
                "advisory": reasoning.get("advisory", {}),
            },
            tokens=reasoning.get("tokens", 0),
            notes=f"agent v{self.VERSION}",
            path=self.db_path,
        )
        return {"run_id": run_id, "deal_id": scored.get("id", "")}

    # -- learn ---------------------------------------------------------------

    def learn(
        self,
        deal_id: str,
        stage: str,
        outcome: str,
        lesson: str = "",
        weight_delta: Optional[dict] = None,
    ) -> str:
        """STUB: ingest a deal outcome to recalibrate weights over time.

        TODO(next-phase): use accumulated learnings to (a) propose adjustments to
        scoring_v7.V7_WEIGHTS, (b) append distilled lessons to directive.md's
        LEARNINGS section via the directive-sync bridge. For now it just records
        the outcome feedback so the signal is captured from day one.
        """
        return memory.record_learning(
            deal_id=deal_id, stage=stage, outcome=outcome,
            lesson=lesson, weight_delta=weight_delta, path=self.db_path,
        )

    # -- full loop -----------------------------------------------------------

    def run_deal(self, deal: DealV7, enrichment: Optional[dict] = None) -> dict:
        """Run one full observe -> reason -> act pass and return the result.

        (learn() is event-driven — triggered later when a deal outcome lands —
        so it is not part of the synchronous scoring pass.)
        """
        context = self.observe(deal, enrichment)
        reasoning = self.reason(context)
        action = self.act(context, reasoning)
        return {
            "deal": reasoning["scored_deal"],
            "run_id": action["run_id"],
            "tokens": reasoning["tokens"],
            "advisory": reasoning["advisory"],
        }
