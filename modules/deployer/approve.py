"""
EVA Deployer — the approve-then-ship gate for live-site deploys (Slack one-tap).

The ``vercel_prod`` action ships the live marketing site
(https://eva-acquisition.mangotec.ai). That is irreversible in the sense that
matters — it replaces what visitors and prospects see — so it never ships on its
own. When the landing repo's remote is ahead, the deploy is recorded as
``pending_approval`` and this module posts a one-tap approval request to the
founder's Slack (the same channel + approval pattern social-publish / local-exec
use), describing the target repo, old→new SHA, and a changed-files summary, with
a launcher approval link. The founder replies / reacts, or hits
``POST /deployer/approve``; only then does ``vercel --prod`` run. If nobody
approves within the timeout, it auto-expires and the old version stays live.

Only ``vercel_prod`` is gated. ``pull_and_restart`` (restarting Eva's own local
services) is left untouched — it is low-stakes and already idle-gated.

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

logger = logging.getLogger("deployer.approve")

# The social-publish module is a sibling dir; import its Slack client +
# credentials directly (same approach as local-exec / social-scheduler reusing
# it) rather than re-implementing a Slack transport or config loader here.
_SOCIAL_DIR = os.path.join(os.path.dirname(__file__), "..", "social-publish")
if os.path.abspath(_SOCIAL_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SOCIAL_DIR))


def _launcher_base() -> str:
    return os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768").rstrip("/")


def approval_link(deploy_id: str) -> str:
    return f"{_launcher_base()}/deployer/approve/{deploy_id}"


def _changed_preview(deploy: dict) -> str:
    """A short changed-files summary for the Slack request."""
    summary = (deploy.get("changed_summary") or "").strip()
    return summary or "(no file list available)"


@runtime_checkable
class ApprovalNotifier(Protocol):
    def notify(self, deploy: dict) -> dict: ...


class StubApprovalNotifier:
    """Offline notifier — records requests in memory, no Slack."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def notify(self, deploy: dict) -> dict:
        self.requests.append(deploy)
        return {"ok": True, "stub": True, "deploy_id": deploy.get("id")}


class SlackApprovalNotifier:
    """Live notifier — posts a one-tap approval request to the founder's Slack."""

    def notify(self, deploy: dict) -> dict:
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

        deploy_id = deploy.get("id", "?")
        target = deploy.get("target", "?")
        repo = deploy.get("repo", "?")
        old_sha = (deploy.get("old_sha") or "")[:7]
        new_sha = (deploy.get("new_sha") or "")[:7]
        changed = _changed_preview(deploy)
        text = (
            f"*🚀 Eva wants to ship the live site* (`{target}` — deploy `{deploy_id}`)\n"
            f"This will run `vercel --prod` on *{repo}* and replace what visitors "
            f"see. It will NOT ship until you approve it.\n"
            f"`{old_sha}` → `{new_sha}`\n"
            f"Changed:\n```\n{changed}\n```\n"
            f"*To approve:* reply `approve` / react :white_check_mark:, "
            f"or open {approval_link(deploy_id)}\n"
            f"A deploy that is not approved is never shipped — the old version stays live."
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
        use_stub = os.environ.get("EVA_DEPLOYER_OFFLINE") == "1"
    return StubApprovalNotifier() if use_stub else SlackApprovalNotifier()


__all__ = [
    "ApprovalNotifier", "StubApprovalNotifier", "SlackApprovalNotifier",
    "build_notifier", "approval_link",
]
