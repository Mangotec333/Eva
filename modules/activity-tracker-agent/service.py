"""
EVA Activity-Tracker-Agent — service layer.

One capability: ``run_daily_digest()`` — reads today's eva-state activity,
builds the digest (engine.build_digest), persists it, emits it back to
eva-state so Diracatron and every other lobe see it, and fires a best-effort
Slack alert when there's revenue traction to double down on.

Resilient by design: every eva-state / Slack call is wrapped so a downstream
outage never crashes a run. Offline-safe with ``EVA_ACTIVITY_OFFLINE=1``.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import store
from engine import build_digest
from models import STATUS_DOUBLE_DOWN, STATUS_RED_FLAG
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("activity_tracker.service")


def slack_alert(text: str) -> dict:
    """Best-effort Slack alert via modules/social-publish/slack_client.py —
    imported lazily so the client is never duplicated (same pattern as
    idea-generator-agent / finance-tracker)."""
    social_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "social-publish")
    if social_dir not in sys.path:
        sys.path.insert(0, social_dir)
    try:
        import slack_client  # type: ignore  # noqa: PLC0415
    except Exception as exc:
        return {"ok": False, "error": f"slack_client unavailable: {exc}"}
    if not slack_client.is_configured():
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    try:
        return slack_client.post_message(text)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


class ActivityTrackerService:
    def __init__(self, *, state: StateLedgerClient | None = None,
                 offline: bool | None = None) -> None:
        self.offline = offline if offline is not None else os.environ.get("EVA_ACTIVITY_OFFLINE") == "1"
        self.state = state or build_state_client(offline=self.offline)

    def run_daily_digest(self, *, date: str | None = None) -> dict:
        """Build + persist + emit the digest for ``date`` (default: today,
        UTC). Reads every eva-state event with a timestamp on that day."""
        target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        since = f"{target_date}T00:00:00+00:00"
        try:
            events = self.state.read_events(since=since, limit=5000)
        except Exception as exc:  # ledger down — report the gap, don't crash
            logger.warning("eva-state read_events failed: %s", exc)
            events = []
        # belt-and-suspenders: keep only events actually dated `target_date`,
        # in case the ledger's `since` filter is looser than expected.
        events = [e for e in events if str(e.get("timestamp") or "").startswith(target_date)] or events

        digest = build_digest(events, date=target_date)
        payload = digest.model_dump()

        try:
            store.save_digest(payload)
        except Exception as exc:
            logger.warning("digest_runs persist failed: %s", exc)

        try:
            self.state.emit(
                event_type="activity_digest_ready",
                summary=f"[{digest.status}] {digest.total_events} events, "
                        f"goal-track share {digest.goal_track_share:.0%}",
                payload=payload,
            )
        except Exception as exc:
            logger.warning("eva-state emit failed for activity_digest_ready: %s", exc)

        if digest.status == STATUS_DOUBLE_DOWN:
            try:
                self.state.emit(
                    event_type="revenue_traction_detected",
                    summary=digest.double_down_recommendation or "Revenue traction detected",
                    payload=payload,
                )
            except Exception as exc:
                logger.warning("eva-state emit failed for revenue_traction_detected: %s", exc)

            alert_text = (
                f":moneybag: EVA activity tracker — REVENUE TRACTION on "
                f"{target_date}.\n{digest.double_down_recommendation}"
            )
            slack = slack_alert(alert_text)
            payload["slack_ok"] = bool(slack.get("ok"))

        elif digest.status == STATUS_RED_FLAG:
            try:
                self.state.emit(
                    event_type="activity_red_flag",
                    summary="; ".join(digest.course_correction_notes)[:500],
                    payload=payload,
                )
            except Exception as exc:
                logger.warning("eva-state emit failed for activity_red_flag: %s", exc)

            alert_text = (
                f":rotating_light: EVA activity tracker RED FLAG — {target_date}.\n"
                + "\n".join(f"• {n}" for n in digest.course_correction_notes)
            )
            slack = slack_alert(alert_text)
            payload["slack_ok"] = bool(slack.get("ok"))

        return payload

    def get_digest(self, date: str) -> dict | None:
        return store.get_digest(date)

    def list_digests(self, *, limit: int = 30) -> list[dict]:
        return store.list_digests(limit=limit)


__all__ = ["ActivityTrackerService", "slack_alert"]
