"""
EVA Idea-Generator-Agent — service layer.

Two capabilities, one module:
  1. score_idea()  — score one venture idea against goal + portfolio fit +
     demand + effort + revenue, persist it, emit to eva-state so every other
     lobe (Diracatron included) sees it on the shared timeline.
  2. run_alignment_check() — daily system-wide drift check: read recent
     eva-state activity, compute goal-track share + low-synergy-build count,
     emit a RED_FLAG event (+ best-effort Slack alert) when Eva's actual
     activity is drifting off the Storeys/Mangotec thesis.

Resilient by design: every eva-state / Slack call is wrapped so a downstream
outage never crashes a scan or a scoring call. Offline-safe with
``EVA_IDEA_OFFLINE=1`` (sandbox default is set explicitly by the caller/tests,
not implied here).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import store
from alignment import build_digest
from engine import score_idea as engine_score_idea
from models import IdeaInput, IdeaScoreResult
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("idea_generator.service")


def slack_alert(text: str) -> dict:
    """Best-effort Slack alert via modules/social-publish/slack_client.py.

    Imported lazily from the sibling module so we never duplicate the client
    (same pattern as modules/finance-tracker/finance_tracker.py:slack_alert).
    Returns honest ``{ok: False, ...}`` when the token/module is missing —
    no network is touched in that case.
    """
    import sys
    social_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "social-publish")
    if social_dir not in sys.path:
        sys.path.insert(0, social_dir)
    try:
        import slack_client  # type: ignore  # noqa: PLC0415
    except Exception as exc:  # module/dep missing
        return {"ok": False, "error": f"slack_client unavailable: {exc}"}
    if not slack_client.is_configured():
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    try:
        return slack_client.post_message(text)
    except Exception as exc:  # network down — never crash the caller
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


class IdeaGeneratorService:
    def __init__(self, *, state: StateLedgerClient | None = None,
                 offline: bool | None = None) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_IDEA_OFFLINE") == "1")
        self.state = state or build_state_client(offline=self.offline)
        self.last_digest: dict | None = None

    # -- idea scoring ---------------------------------------------------------

    def score_idea(self, idea: IdeaInput) -> IdeaScoreResult:
        result = engine_score_idea(idea)
        payload = result.model_dump()

        try:
            store.save_idea_result(payload)
        except Exception as exc:  # local persistence failure — never crash
            logger.warning("idea_runs persist failed: %s", exc)

        try:
            self.state.emit(
                event_type="idea_scored",
                summary=f"[{result.recommendation}] {result.title} "
                        f"(composite {result.composite_score})",
                entity_id=result.idea_id,
                payload=payload,
            )
        except Exception as exc:  # ledger down — scoring still succeeds
            logger.warning("eva-state emit failed for idea_scored: %s", exc)

        if result.flags:
            try:
                self.state.emit(
                    event_type="idea_flag_raised",
                    summary=f"{len(result.flags)} flag(s) on '{result.title}'",
                    entity_id=result.idea_id,
                    payload={"flags": result.flags},
                )
            except Exception as exc:
                logger.warning("eva-state emit failed for idea_flag_raised: %s", exc)

        return result

    def list_idea_runs(self, *, idea_id: str | None = None, limit: int | None = None) -> list[dict]:
        return store.list_idea_runs(idea_id=idea_id, limit=limit)

    # -- alignment / red-flag digest -----------------------------------------

    def run_alignment_check(self, *, window_days: int = 7) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        try:
            events = self.state.read_events(since=since, limit=2000)
        except Exception as exc:  # ledger down — report the gap, don't crash
            logger.warning("eva-state read_events failed: %s", exc)
            events = []

        digest = build_digest(events, window_days=window_days)
        payload = digest.model_dump()

        try:
            store.save_digest(payload)
        except Exception as exc:
            logger.warning("digest_runs persist failed: %s", exc)

        try:
            self.state.emit(
                event_type="alignment_digest",
                summary=f"[{digest.status}] goal-track share "
                        f"{digest.goal_track_share:.0%} over {window_days}d",
                payload=payload,
            )
        except Exception as exc:
            logger.warning("eva-state emit failed for alignment_digest: %s", exc)

        if digest.status == "RED_FLAG":
            try:
                self.state.emit(
                    event_type="alignment_red_flag",
                    summary="; ".join(digest.red_flags)[:500],
                    payload=payload,
                )
            except Exception as exc:
                logger.warning("eva-state emit failed for alignment_red_flag: %s", exc)

            alert_text = (
                f":rotating_light: EVA alignment RED FLAG — goal-track share "
                f"{digest.goal_track_share:.0%} over last {window_days}d.\n"
                + "\n".join(f"• {f}" for f in digest.red_flags)
            )
            slack = slack_alert(alert_text)
            payload["slack_ok"] = bool(slack.get("ok"))
        else:
            payload["slack_ok"] = None

        self.last_digest = payload
        return payload

    def list_digests(self, *, limit: int = 30) -> list[dict]:
        return store.list_digests(limit=limit)


__all__ = ["IdeaGeneratorService", "slack_alert"]
