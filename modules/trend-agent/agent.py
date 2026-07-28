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
from app_scan_engine import APP_SCAN_ENGINE_VERSION, run_app_scan
from app_models import AppScanRunInput, AppScanRunResult
from competitor_scan_engine import (
    CASES_DIR,
    COMPETITOR_SCAN_ENGINE_VERSION,
    run_competitor_scan,
)
from competitor_models import CompetitorScanRunInput, CompetitorScanRunResult

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

    def run_app_scan(self, inp: AppScanRunInput) -> AppScanRunResult:
        """App Category Scan mode: top-10-per-category app research ->
        aggregated second-look/opportunity report for short-term revenue.
        Recommended cadence: monthly (see directive.md)."""
        result = run_app_scan(inp)
        run_id = str(uuid.uuid4())
        memory.save_app_scan_run(
            run_id=run_id,
            run_label=inp.run_label,
            input_json=inp.model_dump_json(),
            result_json=result.model_dump_json(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._emit_app_scan_run(run_id, inp, result)
        return result

    def _emit_app_scan_run(self, run_id: str, inp: AppScanRunInput, result: AppScanRunResult) -> None:
        self.state_client.emit(
            event_type="app_scan_run_completed",
            summary=(f"App scan '{inp.run_label}' -> {result.total_second_look_apps}/"
                     f"{result.total_apps_scanned} apps flagged worth a second look"),
            entity_id=run_id,
            payload={
                "run_label": inp.run_label,
                "total_apps_scanned": result.total_apps_scanned,
                "total_second_look_apps": result.total_second_look_apps,
                "top_priority_picks": [p.name for p in result.top_priority_picks[:5]],
            },
        )
        high_opportunity = [c.category for c in result.categories if c.opportunity_tier == "HIGH"]
        if high_opportunity:
            self.state_client.emit(
                event_type="app_scan_high_opportunity",
                summary=f"HIGH opportunity tier categories this run: {', '.join(high_opportunity)}",
                entity_id=run_id,
                payload={"categories": high_opportunity, "urgent": True},
            )


    def run_competitor_scan(
        self, inp: CompetitorScanRunInput, cases_dir: str = CASES_DIR
    ) -> CompetitorScanRunResult:
        """Competitor Scan mode: diff this month's AI-agent-directory snapshot
        against the previous month's and flag new entrants into EVA's buy-side
        deal-sourcing/underwriting niche. Deterministic and network-free (the
        HTTP fetch happens upstream in competitor_fetch.py), so a run costs ~$0
        in LLM credits. Recommended cadence: monthly (see directive.md)."""
        result = run_competitor_scan(inp, cases_dir=cases_dir)
        run_id = str(uuid.uuid4())
        memory.save_competitor_scan_run(
            run_id=run_id,
            scan_date=inp.scan_date,
            verdict=result.verdict,
            input_json=inp.model_dump_json(),
            result_json=result.model_dump_json(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._emit_competitor_scan_run(run_id, inp, result)
        return result

    def _emit_competitor_scan_run(
        self, run_id: str, inp: CompetitorScanRunInput, result: CompetitorScanRunResult
    ) -> None:
        """Every scan is logged (routine). An ALERT verdict is additionally
        emitted as ``competitor_threat_detected`` with ``urgent`` — the same
        payload flag Diracatron already uses to raise triage priority, so a new
        direct competitor surfaces on the existing alert path with no new
        notification channel.
        """
        self.state_client.emit(
            event_type="competitor_scan_run_completed",
            summary=(f"Competitor scan {inp.scan_date} -> {result.verdict} "
                     f"({len(result.new_entrants)} new of {result.total_entries} entries)"),
            entity_id=run_id,
            payload={
                "scan_date": inp.scan_date,
                "previous_scan_date": result.previous_scan_date,
                "verdict": result.verdict,
                "total_entries": result.total_entries,
                "new_entrants": [e.name for e in result.new_entrants],
            },
        )
        if result.verdict == "ALERT":
            self.state_client.emit(
                event_type="competitor_threat_detected",
                summary=(f"ALERT: new direct competitor(s) in EVA's buy-side deal-sourcing niche "
                         f"({inp.scan_date}): {', '.join(e.name for e in result.new_entrants)}"),
                entity_id=run_id,
                payload={
                    "scan_date": inp.scan_date,
                    "verdict": result.verdict,
                    "new_entrants": [
                        {"name": e.name, "url": e.url, "description": e.description}
                        for e in result.new_entrants
                    ],
                    "flags": result.flags,
                    "urgent": True,
                },
            )


def engine_version() -> str:
    return ENGINE_VERSION


def app_scan_engine_version() -> str:
    return APP_SCAN_ENGINE_VERSION


def competitor_scan_engine_version() -> str:
    return COMPETITOR_SCAN_ENGINE_VERSION
