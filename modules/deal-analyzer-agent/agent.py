"""
EVA Deal Analyzer Agent — autonomous LLM-loop microservice
==========================================================

This is the FIRST instance of Eva's new agentic operating model: every task
becomes an autonomous LLM-loop microservice agent that learns over time.

THE LOOP (cost-gate cascade, simplified):

  observe()  gather the deal + free per-niche enrichment into a context
  radar      Gate 1 — cheap free checks drop unfit deals BEFORE any spend
  score()    the DETERMINISTIC v7 core (scoring_v7.analyze_deal_v7) — the
             AUTHORITATIVE, free engine. It never depends on a brain.
  route      route_deal() -> SHORTLIST (>= threshold) or LOG_ONLY
  act()      persist the scored deal + run (tier, gate trace, provider, tokens)
  learn()    record deal outcomes (passed / LOI / closed) to recalibrate later

Claude is NOT a per-deal hot-loop brain. It is an OPTIONAL second-opinion applied
ONLY to SHORTLIST deals (deep-dive path) when second_opinion is enabled AND a key
is present — or to every survivor in testing mode (to collect training data).
LOG_ONLY deals are scored + persisted with NO brain (tokens=0).

SEPARATION OF CONCERNS (important): the v7 scoring engine is pure and fully
testable without a brain. Claude is an ADDITIVE reasoning layer, never a
dependency of the numeric core. With a NoopClaudeClient (no key) the agent still
produces complete, deterministic scores and logs tokens=0. The BrainClient
Protocol seam is kept so a brain can be re-plugged (or swapped) later.
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
from cost_gate import (
    CostTier,
    is_testing_mode,
    load_config,
    route_deal,
    second_opinion_enabled,
    should_second_opinion,
)
from models import DealV7, KnownOutcome
from radar import radar_filter
from scoring_v7 import analyze_deal_v7

from services.remote.claude import (  # noqa: E402  (path bootstrap above)
    BrainClient,
    NoopClaudeClient,
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
    """Autonomous observe -> radar -> enrich -> score -> route -> act/learn loop.

    Cost-gate cascade (simplified): the deterministic v7 score is authoritative
    and FREE. A cheap Gate-1 radar drops unfit deals first; free per-niche
    enrichment feeds v7; ``route_deal`` sorts survivors into SHORTLIST vs
    LOG_ONLY. Claude is NOT a per-deal hot-loop brain — it is an OPTIONAL
    second-opinion on the shortlist, gated behind should_second_opinion() AND
    second_opinion.enabled AND a configured key. Testing mode opens all gates to
    collect labeled training_observation records.
    """

    VERSION = "0.3.0"

    def __init__(
        self,
        brain: Optional[BrainClient] = None,
        db_path: str = memory.DB_PATH,
        *,
        enrich_fn: Optional[EnrichFn] = None,
        paid_enrich_fn: Optional[EnrichFn] = None,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 1024,
        config: Optional[dict] = None,
        second_opinion: Optional[bool] = None,
    ):
        # brain defaults to the env-resolved client (Noop when no key), so the
        # agent is fully functional — deterministic-only — without a key.
        self.brain: BrainClient = brain or make_claude_client()
        self.enrich_fn = enrich_fn
        self.paid_enrich_fn = paid_enrich_fn      # shortlist-only deep-dive seam
        self.model = model
        self.max_tokens = max_tokens
        self.db_path = db_path

        # Cost-gate config (thresholds, allowed categories, second-opinion flag,
        # testing mode). All routing decisions read from here — no magic numbers.
        self.config = config if config is not None else load_config()
        self.testing_mode = is_testing_mode(self.config)
        self.second_opinion_enabled = (
            second_opinion if second_opinion is not None
            else second_opinion_enabled(self.config)
        )
        self.brain_provider = type(self.brain).__name__
        self.brain_configured = self._resolve_brain_configured()

        memory.init_db(self.db_path)

    def _resolve_brain_configured(self) -> bool:
        """Whether the brain can actually reach a model (vs a Noop/keyless stub)."""
        configured = getattr(self.brain, "configured", None)
        if configured is not None:
            return bool(configured)
        return not isinstance(self.brain, NoopClaudeClient)

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

    # -- score (deterministic, authoritative, free) --------------------------

    def score(self, context: dict) -> DealV7:
        """Run the deterministic v7 engine. Authoritative, free, no brain.

        This is the ONLY scoring path in the hot loop — it never depends on a
        brain. Claude (if it runs at all) is an additive second-opinion applied
        AFTER routing, never a dependency of the numeric core.
        """
        deal = DealV7(**context["deal"])
        enrichment = context.get("enrichment") or {}
        return analyze_deal_v7(deal, enrichment=enrichment or None)

    # -- second opinion (OPTIONAL, shortlist / testing only) -----------------

    def _brain_should_run(self, tier: CostTier) -> bool:
        """Gate the OPTIONAL Claude call. Never per-deal in the default hot path.

        Requires a configured brain, then either testing mode (full treatment on
        every survivor to collect training data) OR a SHORTLIST deal with the
        second_opinion flag enabled. LOG_ONLY deals never call the brain.
        """
        if not self.brain_configured:
            return False
        if self.testing_mode:
            return True
        return tier is CostTier.SHORTLIST and self.second_opinion_enabled

    def _second_opinion(self, scored: DealV7, enrichment: dict,
                        directive: str) -> tuple[dict, int]:
        """Call the brain for advisory judgement on top of the v7 scores.

        Returns (advisory, tokens). A brain error degrades to a stub advisory;
        callers still get a complete deterministic result.
        """
        system = build_reasoning_system()
        user = build_reasoning_user(scored, enrichment, directive)
        response = self.brain.complete(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=self.max_tokens,
            model=self.model,
        )
        error = response.get("error")
        if error:
            advisory: dict[str, Any] = {"_brain_error": error, "_stub": True}
        else:
            advisory = _parse_advisory(response.get("content", ""))
        return advisory, total_tokens(response.get("usage"))

    # -- act -----------------------------------------------------------------

    def act(self, context: dict, reasoning: dict,
            known_outcome: Optional[dict] = None) -> dict:
        """Persist the scored deal and the run to memory.

        The run row now carries the cost-gate trace: tier, radar reasons, the
        brain provider actually used, and token usage (0 when no brain ran).
        """
        scored = reasoning["scored_deal"]
        memory.save_deal(scored, path=self.db_path)
        run_id = memory.save_run(
            deal_id=scored.get("id", ""),
            inputs={"deal": context["deal"], "enrichment": context.get("enrichment", {})},
            outputs={
                "overall_score": scored.get("overall_score"),
                "category_v2": scored.get("category_v2"),
                "tier": reasoning.get("tier"),
                "gate_trace": reasoning.get("gate_trace", {}),
                "brain_provider": reasoning.get("brain_provider", "none"),
                "advisory": reasoning.get("advisory", {}),
                "known_outcome": known_outcome or {},
            },
            tokens=reasoning.get("tokens", 0),
            notes=f"agent v{self.VERSION} tier={reasoning.get('tier')}",
            path=self.db_path,
        )
        return {"run_id": run_id, "deal_id": scored.get("id", "")}

    def _log_drop(self, deal: DealV7, reasons: list) -> dict:
        """Log a radar-dropped deal (no scoring, no brain) and return the result."""
        deal_dump = deal.model_dump()
        gate_trace = {"radar_passed": False, "radar_reasons": reasons,
                      "tier": "DROPPED", "testing_mode": self.testing_mode}
        run_id = memory.save_run(
            deal_id=deal_dump.get("id", ""),
            inputs={"deal": deal_dump},
            outputs={"tier": "DROPPED", "gate_trace": gate_trace, "brain_provider": "none"},
            tokens=0,
            notes=f"agent v{self.VERSION} radar-drop",
            path=self.db_path,
        )
        return {"deal": deal_dump, "run_id": run_id, "tokens": 0, "advisory": {},
                "tier": "DROPPED", "gate_trace": gate_trace, "dropped": True}

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

    def run_deal(
        self,
        deal: DealV7,
        enrichment: Optional[dict] = None,
        known_outcome: Optional[Any] = None,
    ) -> dict:
        """Run one full cost-gate cascade pass and return the result.

        Flow: radar (Gate 1, drop+log on fail unless testing) -> observe (free
        per-niche enrichment) -> v7 score (authoritative) -> route_deal ->
        optional shortlist/testing deep-dive (paid enrichment re-score + Claude
        second-opinion) -> act (persist tier + gate trace + provider + tokens).

        ``known_outcome`` (a KnownOutcome / dict) labels a CLOSED deal for
        training; it is persisted but does not affect routing.
        """
        # --- Gate 1: radar (free). Drop + log unfit deals before spending. ---
        passed, reasons = radar_filter(deal, config=self.config)
        if not passed and not self.testing_mode:
            return self._log_drop(deal, reasons)

        known = self._coerce_known_outcome(known_outcome)

        # --- observe: free per-niche enrichment feeds v7 ---------------------
        context = self.observe(deal, enrichment)
        enr = dict(context.get("enrichment") or {})

        # --- score: deterministic v7 (authoritative, free) -------------------
        scored = self.score(context)
        tier = route_deal(scored, scored.overall_score, self.config)

        gate_trace: dict[str, Any] = {
            "radar_passed": passed,
            "radar_reasons": reasons,
            "tier": tier.value,
            "testing_mode": self.testing_mode,
            "paid_enrichment": False,
        }

        # --- deep dive (shortlist OR testing): paid enrichment + re-score ----
        deep_dive = tier is CostTier.SHORTLIST or self.testing_mode
        if deep_dive and self.paid_enrich_fn is not None:
            try:
                paid = dict(self.paid_enrich_fn(deal.name) or {})
            except Exception:  # noqa: BLE001 — paid enrichment must not break loop
                paid = {}
            if paid:
                enr = {**enr, **paid}
                context["enrichment"] = enr
                scored = self.score(context)
                tier = route_deal(scored, scored.overall_score, self.config)
                gate_trace["paid_enrichment"] = True
                gate_trace["tier"] = tier.value

        # --- optional Claude second-opinion (NOT a hot-loop brain) -----------
        do_brain = self._brain_should_run(tier)
        gate_trace["second_opinion"] = do_brain
        advisory: dict[str, Any] = {}
        tokens = 0
        if do_brain:
            advisory, tokens = self._second_opinion(scored, enr, context.get("directive", ""))
        advisory.setdefault("confidence", 0.0)

        reasoning = {
            "scored_deal": scored.model_dump(),
            "advisory": advisory,
            "tokens": tokens,
            "tier": tier.value,
            "gate_trace": gate_trace,
            "brain_provider": self.brain_provider if do_brain else "none",
        }
        action = self.act(context, reasoning, known_outcome=known)

        # --- testing mode: persist a labeled training_observation ------------
        if self.testing_mode:
            memory.save_training_observation(
                deal_id=scored.id,
                tier=tier.value,
                v7_score=scored.overall_score,
                features=scored.model_dump(),
                enrichment=enr,
                brain_output={"advisory": advisory, "tokens": tokens,
                              "provider": reasoning["brain_provider"]},
                gate_trace=gate_trace,
                known_outcome=known,
                path=self.db_path,
            )

        return {
            "deal": reasoning["scored_deal"],
            "run_id": action["run_id"],
            "tokens": tokens,
            "advisory": advisory,
            "tier": tier.value,
            "gate_trace": gate_trace,
            "dropped": False,
        }

    @staticmethod
    def _coerce_known_outcome(known_outcome: Optional[Any]) -> dict:
        """Accept a KnownOutcome / dict / None -> a plain dict (empty when absent)."""
        if known_outcome is None:
            return {}
        if isinstance(known_outcome, KnownOutcome):
            return known_outcome.to_dict()
        if isinstance(known_outcome, dict):
            return dict(known_outcome)
        return {}

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
