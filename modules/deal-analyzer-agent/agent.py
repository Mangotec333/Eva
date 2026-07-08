"""
EVA Deal Analyzer Agent — autonomous LLM-loop microservice
==========================================================

This is the FIRST instance of Eva's new agentic operating model: every task
becomes an autonomous LLM-loop microservice agent that learns over time.

THE LOOP:  observe() -> reason() -> act() -> learn()

  observe()  gather the deal + any (cached) enrichment into a structured context
  reason()   score the deal. The DETERMINISTIC core (scoring_v7.analyze_deal_v7)
             is authoritative and runs LOCALLY (T0, free). THEN the reasoning
             brain (Claude / Anthropic) is called for the JUDGEMENT layer —
             edge-case rationale, lever assessments, confidence flags — with the
             deterministic scores passed in as context. Claude is metered (T2)
             and stateless per call; EVA holds the loop context locally.
  act()      persist the scored deal + the run (with token usage) to memory.db
  learn()    record deal outcomes (passed / LOI / closed) to recalibrate later

SEPARATION OF CONCERNS (important): the v7 scoring engine is pure and fully
testable without a brain. Claude is an ADDITIVE reasoning layer, never a
dependency of the numeric core. With a NoopClaudeClient (no key) the agent still
produces complete, deterministic scores and logs tokens=0.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

# The module runs "flat" (cwd = this dir), so put the repo root on the path to
# reach the shared services/ package for the Claude reasoning transport.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import memory
from models import DealV7
from scoring_v7 import analyze_deal_v7

from services.remote.claude import (  # noqa: E402  (path bootstrap above)
    ClaudeClient,
    make_claude_client,
    total_tokens,
)

DIRECTIVE_PATH = os.path.join(os.path.dirname(__file__), "directive.md")

# An enrichment gatherer maps a niche string -> flat enrichment kwargs dict
# (the shape analyze_deal_v7 consumes). Injected so the agent core stays free of
# the Perplexity transport; see enrichment.gather_enrichment.
EnrichFn = Callable[[str], dict]

# A deal source yields DealV7 candidates for the continuous loop.
DealSource = Callable[[], Iterable[DealV7]]


def build_reasoning_system() -> str:
    """The stable system prompt for the reasoning brain."""
    return (
        "You are the EVA Deal Analyzer Agent's reasoning layer. A deterministic "
        "v7 scoring engine has ALREADY produced authoritative numeric scores. Your "
        "job is the judgement layer that sits on top: qualitative rationale for "
        "edge cases, assessment of the growth levers, and confidence flags where "
        "the data looks thin. Do NOT restate or override the numbers.\n\n"
        "Respond with ONLY a JSON object of the form:\n"
        '{"qualitative_notes": str, "lever_assessments": {lever: str}, '
        '"confidence_flags": [str], "confidence": float (0-1)}'
    )


def build_reasoning_user(deal: DealV7, enrichment: dict, directive: str) -> str:
    """The per-deal user message: deterministic scores + context for Claude."""
    return (
        f"LIVE DIRECTIVE (excerpt):\n{directive[:1500]}\n\n"
        f"DEAL: {deal.name} ({deal.category} -> {deal.category_v2}), "
        f"${deal.monthly_net:,.0f}/mo, {deal.annual_multiple:g}x, {deal.age_years:g}yr.\n\n"
        "DETERMINISTIC v7 SCORES (authoritative):\n"
        f"  overall_score: {deal.overall_score}\n"
        f"  cashflow: {deal.cashflow_score}  profit_potential: {deal.profit_potential_score}\n"
        f"  exit_potential: {deal.exit_potential_score}  moat: {deal.moat_score}\n"
        f"  tam: {deal.tam_score}  competitor_analysis: {deal.competitor_analysis_score}\n"
        f"  ai_proof: {deal.ai_proof_score}  risk: {deal.risk_score}\n"
        f"  profit_lever_scores: {json.dumps(deal.profit_lever_scores)}\n\n"
        f"ENRICHMENT PRESENT: {sorted((enrichment or {}).keys())}\n"
        f"RESEARCH LEVEL: {deal.research_level}\n\n"
        "Return the JSON judgement now."
    )


def _parse_advisory(content: str) -> dict:
    """Parse Claude's JSON judgement, tolerating prose/code-fence wrapping."""
    text = (content or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {"qualitative_notes": content.strip()}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"qualitative_notes": content.strip()}


# ===========================================================================
# THE AGENT
# ===========================================================================

class DealAnalyzerAgent:
    """Autonomous observe -> reason -> act -> learn loop for deal scoring."""

    VERSION = "0.2.0"

    def __init__(
        self,
        brain: Optional[ClaudeClient] = None,
        db_path: str = memory.DB_PATH,
        *,
        enrich_fn: Optional[EnrichFn] = None,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 1024,
    ):
        # brain defaults to the env-resolved client (Noop when no key), so the
        # agent is fully functional — deterministic-only — without a key.
        self.brain: ClaudeClient = brain or make_claude_client()
        self.enrich_fn = enrich_fn
        self.model = model
        self.max_tokens = max_tokens
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
        """Assemble the structured context for a reasoning pass.

        When no enrichment is passed and an ``enrich_fn`` is configured, the
        agent gathers (cached) enrichment for the deal's niche. Gathering is
        best-effort: any failure degrades to no enrichment rather than aborting.
        """
        enr = dict(enrichment or {})
        if not enr and self.enrich_fn is not None:
            try:
                enr = dict(self.enrich_fn(deal.name) or {})
            except Exception:  # noqa: BLE001 — enrichment must never break the loop
                enr = {}
        return {
            "deal": deal.model_dump(),
            "enrichment": enr,
            "directive": self.load_directive(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    # -- reason --------------------------------------------------------------

    def reason(self, context: dict) -> dict:
        """Score the deal, then call Claude for the judgement layer.

        The deterministic v7 engine is authoritative and runs first, locally.
        Claude receives the scores as context and returns advisory judgement. A
        Noop brain (no key) yields an empty advisory with tokens=0.
        """
        deal = DealV7(**context["deal"])
        enrichment = context.get("enrichment") or {}

        # 1) Deterministic core — always runs, no network/brain.
        scored = analyze_deal_v7(deal, enrichment=enrichment or None)

        # 2) Reasoning brain (Claude) — advisory judgement on top of the scores.
        system = build_reasoning_system()
        user = build_reasoning_user(scored, enrichment, context.get("directive", ""))
        response = self.brain.complete(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=self.max_tokens,
            model=self.model,
        )

        error = response.get("error")
        advisory: dict[str, Any]
        if error:
            advisory = {"_brain_error": error, "_stub": True}
        else:
            advisory = _parse_advisory(response.get("content", ""))
        advisory.setdefault("confidence", 0.0)

        return {
            "scored_deal": scored.model_dump(),
            "advisory": advisory,
            "tokens": total_tokens(response.get("usage")),
            "stop_reason": response.get("stop_reason"),
        }

    # -- act -----------------------------------------------------------------

    def act(self, context: dict, reasoning: dict) -> dict:
        """Persist the scored deal and the run (with token usage) to memory."""
        scored = reasoning["scored_deal"]
        memory.save_deal(scored, path=self.db_path)
        run_id = memory.save_run(
            deal_id=scored.get("id", ""),
            inputs={"deal": context["deal"], "enrichment": context.get("enrichment", {})},
            outputs={
                "overall_score": scored.get("overall_score"),
                "category_v2": scored.get("category_v2"),
                "advisory": reasoning.get("advisory", {}),
                "stop_reason": reasoning.get("stop_reason"),
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
        """Record a deal outcome so the learning loop can recalibrate later.

        This is the raw feedback capture; ``learn.recalibrate()`` reads these
        rows to PROPOSE weight deltas (non-destructively). Distilled lessons are
        fed back into directive.md via the directive-sync bridge
        (services/directive_sync.py).
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

    def run_pipeline(self, deals: Iterable[DealV7]) -> list[dict]:
        """Score a batch of deals through the full loop, one at a time.

        Returns one result dict per deal. A single deal failing is isolated:
        its result carries an ``error`` key and the pipeline continues.
        """
        results: list[dict] = []
        for deal in deals:
            try:
                results.append(self.run_deal(deal))
            except Exception as exc:  # noqa: BLE001 — one bad deal must not abort the batch
                results.append({"deal": {"id": getattr(deal, "id", "")}, "error": str(exc)})
        return results

    def run_loop(
        self,
        source: DealSource,
        *,
        interval_s: float = 60.0,
        max_iterations: Optional[int] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict:
        """Continuous poll -> score loop. This is the LOOP-RUNNER.

        Polls ``source`` for new deals each tick and runs the full pipeline on
        whatever it returns. Runs forever by default; pass ``max_iterations`` to
        bound it (used by tests and one-shot cron ticks). ``source`` is the only
        stubbed seam — plug in deal-scout / connectors here — but the loop itself
        is real: it iterates, scores, and sleeps between empty polls.

        Returns a summary: iterations run and total deals scored.
        """
        iterations = 0
        total_scored = 0
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            batch = list(source() or [])
            if batch:
                total_scored += len(self.run_pipeline(batch))
            elif max_iterations is None or iterations < max_iterations:
                sleep(interval_s)  # nothing new — back off before polling again
        return {"iterations": iterations, "scored": total_scored}
