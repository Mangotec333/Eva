"""
EVA Retro-Agent — service layer.

One capability: ``run_retro()`` — the Monday-morning weekly retrospective.

It (1) reads the eva-state timeline for the retro window (a WIDE read so stale
blockers with no recent event are still seen), (2) reads last week's stated
course-correction priorities from the Weekly Retrospective Log, (3) builds the
Weekly Retro Digest deterministically (``engine.build_retro``), (4) optionally
sharpens ONLY the narrative prose via the brain, (5) persists it to the
append-only ledger (``memory.save_digest``), and (6) emits it back to eva-state
so Diracatron and every other lobe see the digest on the shared timeline.

Resilient by design: every eva-state / brain / persist call is wrapped so a
downstream outage never crashes a run. Offline-safe with ``EVA_RETRO_OFFLINE=1``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import memory
from brain import RetroBrain, make_brain
from engine import build_retro
from models import (
    STATUS_DRIFTING,
    STATUS_REVENUE_WIN,
    STATUS_STALLED_BLOCKER,
)
from retro_log import RetroLogSource, make_retro_log_source
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("retro_agent.service")

# How many days of history to read. The retro window is 7 days, but blockers are
# tracked across their full open lifetime (batch.ai LOI has been stale 7+ weeks),
# so we read a much wider slice and let the engine window shipping/pipeline
# evidence to the 7-day window while keeping blockers over the whole read.
LOOKBACK_DAYS = 120


class RetroService:
    def __init__(self, *, state: Optional[StateLedgerClient] = None,
                 log_source: Optional[RetroLogSource] = None,
                 brain: Optional[RetroBrain] = None,
                 offline: Optional[bool] = None) -> None:
        self.offline = offline if offline is not None else os.environ.get("EVA_RETRO_OFFLINE") == "1"
        self.state = state or build_state_client(offline=self.offline)
        self.log_source = log_source or make_retro_log_source(offline=self.offline)
        self.brain = brain or make_brain(offline=self.offline)

    def _window(self, week_end: Optional[str]) -> tuple[str, str]:
        """Resolve [week_start, week_end]. Default week_end = today (UTC, the
        Monday the retro runs); week_start = 7 days earlier (inclusive)."""
        end_d = None
        if week_end:
            try:
                end_d = datetime.strptime(week_end[:10], "%Y-%m-%d").date()
            except ValueError:
                end_d = None
        if end_d is None:
            end_d = datetime.now(timezone.utc).date()
        start_d = end_d - timedelta(days=7)
        return start_d.isoformat(), end_d.isoformat()

    def run_retro(self, *, week_end: Optional[str] = None) -> dict:
        """Build + persist + emit the Weekly Retro Digest for the window ending
        on ``week_end`` (default: today, UTC)."""
        week_start, week_end_res = self._window(week_end)

        # Wide read so long-stale blockers are still visible (see LOOKBACK_DAYS).
        read_from = (
            datetime.strptime(week_end_res, "%Y-%m-%d").date() - timedelta(days=LOOKBACK_DAYS)
        ).isoformat()
        since = f"{read_from}T00:00:00+00:00"
        try:
            events = self.state.read_events(since=since, limit=10000)
        except Exception as exc:  # ledger down — report the gap, don't crash
            logger.warning("eva-state read_events failed: %s", exc)
            events = []

        # Read last week's stated course-correction priorities. Never raises.
        try:
            log_entry = self.log_source.read_latest_priorities()
        except Exception as exc:  # defensive — source contract says it won't
            logger.warning("retro-log read failed: %s", exc)
            log_entry = None

        prior_priorities = list(log_entry.priorities) if (log_entry and log_entry.ok) else []
        if log_entry is None:
            prior_source = "unavailable"
        elif log_entry.ok:
            prior_source = log_entry.source
        else:
            prior_source = f"{log_entry.source} (no baseline: {log_entry.error})"

        digest = build_retro(
            events,
            week_start=week_start,
            week_end=week_end_res,
            prior_priorities=prior_priorities,
            prior_priorities_source=prior_source,
        )

        # Brain sharpens ONLY the narrative prose — never a status/flag/count.
        try:
            sharpened = self.brain.sharpen(digest.model_dump())
            if sharpened.get("narrative"):
                digest.narrative = sharpened["narrative"]
        except Exception as exc:  # brain must never break the retro
            logger.warning("brain.sharpen failed: %s", exc)

        payload = digest.model_dump()

        try:
            run_id = memory.save_digest(payload)
            payload["run_id"] = run_id
        except Exception as exc:
            logger.warning("retro_runs persist failed: %s", exc)

        self._emit_digest(digest, payload)
        return payload

    def _emit_digest(self, digest, payload: dict) -> None:
        """Emit the digest (always) + a status-specific signal back to eva-state."""
        summary = (
            f"[{digest.status}] shipped={digest.shipped_count} "
            f"revenue_moves={digest.revenue_movement_count} "
            f"stale={len(digest.stale_blockers)} "
            f"priorities={digest.priorities_addressed}/{digest.priorities_total}"
        )
        try:
            self.state.emit(event_type="retro_digest_ready", summary=summary, payload=payload)
        except Exception as exc:
            logger.warning("eva-state emit failed for retro_digest_ready: %s", exc)

        status_event = {
            STATUS_REVENUE_WIN: "retro_revenue_win",
            STATUS_STALLED_BLOCKER: "retro_stalled_blocker",
            STATUS_DRIFTING: "retro_drift_flagged",
        }.get(digest.status)
        if status_event:
            note = digest.drift_note or (
                "; ".join(digest.course_correction_notes)[:500]
                if digest.course_correction_notes else digest.status
            )
            try:
                self.state.emit(event_type=status_event, summary=note[:500], payload=payload)
            except Exception as exc:
                logger.warning("eva-state emit failed for %s: %s", status_event, exc)

    def latest(self) -> Optional[dict]:
        return memory.latest_digest()

    def history(self, *, limit: int = 30) -> list[dict]:
        return memory.list_digests(limit=limit)

    def get(self, run_id: str) -> Optional[dict]:
        return memory.get_digest(run_id)


__all__ = ["RetroService", "LOOKBACK_DAYS"]
