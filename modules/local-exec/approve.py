"""
EVA Local-Exec — the approve-then-run gate (Slack one-tap).

A command that is NOT on the allowlist never runs on its own. Instead the service
records it as ``pending`` and this module posts a one-tap approval request to the
founder's Slack (the same channel + approval pattern social-publish uses), with
the masked command and a launcher approval link. The founder replies / reacts, or
hits ``POST /local-exec/approve``; only then does the command run. If nobody
approves within the timeout, it auto-expires and never runs.

Reuse (imported, not duplicated):
  * ``modules/social-publish/slack_client`` — the tiny stdlib Slack client +
    ``DEFAULT_REVIEW_CHANNEL`` approve-channel pattern.
  * ``modules/social-publish/credentials.build_cfg`` — config-file-primary /
    env-fallback config resolution from ``~/.eva/channels_config.json``.

The notifier is behind a Protocol with a Stub so offline tests never touch Slack.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("local-exec.approve")

# The social-publish module is a sibling dir; import its Slack client +
# credentials directly (same approach as social-scheduler reusing it) rather than
# re-implementing a Slack transport or config loader here.
_SOCIAL_DIR = os.path.join(os.path.dirname(__file__), "..", "social-publish")
if os.path.abspath(_SOCIAL_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SOCIAL_DIR))


def _launcher_base() -> str:
    return os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768").rstrip("/")


def approval_link(run_id: str) -> str:
    return f"{_launcher_base()}/local-exec/approve/{run_id}"


def _shell_preview(run: dict) -> str:
    parts = [run.get("command", "")] + list(run.get("args", []) or [])
    return " ".join(p for p in parts if p)


@runtime_checkable
class ApprovalNotifier(Protocol):
    def notify(self, run: dict) -> dict: ...


class StubApprovalNotifier:
    """Offline notifier — records requests in memory, no Slack."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def notify(self, run: dict) -> dict:
        self.requests.append(run)
        return {"ok": True, "stub": True, "run_id": run.get("id")}


class SlackApprovalNotifier:
    """Live notifier — posts a one-tap approval request to the founder's Slack."""

    def notify(self, run: dict) -> dict:
        try:
            import slack_client  # noqa: PLC0415 — sibling social-publish module
        except Exception as exc:  # ImportError / missing dep — fail safe
            return {"ok": False, "error": f"slack_client unavailable: {exc}"}

        # Touch credentials.build_cfg so config presence is resolved the same way
        # every other surface resolves it (config-file-primary / env fallback).
        try:
            import credentials  # noqa: PLC0415
            credentials.build_cfg()
        except Exception:  # noqa: BLE001 — non-fatal; Slack post is what matters
            pass

        run_id = run.get("id", "?")
        preview = _shell_preview(run)
        cwd = run.get("cwd") or "~"
        text = (
            f"*🖐️ Eva wants to run a command on the Mac* (run `{run_id}`)\n"
            f"This command is NOT on the safe allowlist, so it will NOT run "
            f"until you approve it.\n"
            f"```\n{preview}\n```\n"
            f"cwd: `{cwd}`\n\n"
            f"*To approve:* reply `approve` / react :white_check_mark:, "
            f"or open {approval_link(run_id)}\n"
            f"A run that is not approved is never executed."
        )
        try:
            res = slack_client.post_message(
                text, channel=slack_client.DEFAULT_REVIEW_CHANNEL)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"slack post failed: {exc}"}
        return {"ok": bool(res.get("ok")), "ts": res.get("ts", ""),
                "channel": res.get("channel", ""), "error": res.get("error", "")}


def build_notifier(offline: Optional[bool] = None) -> ApprovalNotifier:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_LOCAL_EXEC_OFFLINE") == "1"
    return StubApprovalNotifier() if use_stub else SlackApprovalNotifier()


__all__ = [
    "ApprovalNotifier", "StubApprovalNotifier", "SlackApprovalNotifier",
    "build_notifier", "approval_link",
]
