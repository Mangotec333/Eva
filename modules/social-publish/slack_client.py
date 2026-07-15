"""
EVA Social-Publish — minimal Slack Web API client.

No third-party Slack SDK exists in the repo, so this is a tiny stdlib-first
client (urllib for all JSON calls) so it works even inside the launcher's
minimal env. ``requests`` is used *only* for the optional multipart image
upload, and its absence is non-fatal.

Auth: bot token from ``SLACK_BOT_TOKEN`` (never hardcoded). The bot must be a
member of the target DM/channel and have scopes:
  * chat:write            — post the draft + status replies
  * reactions:read        — detect the ✅ approval reaction
  * channels:history / groups:history / im:history / mpim:history
                          — detect an 'approve' reply
  * files:write           — (optional) upload the draft image

The approval target is the founder's DM by default; override via env.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Optional

SLACK_API = "https://slack.com/api"

# Founder review DM (task-specified defaults; overridable by env so no PII is
# baked into behaviour beyond a routable default).
DEFAULT_APPROVER_USER_ID = os.environ.get("EVA_SLACK_APPROVER_USER_ID", "U0ARNV5PDRC")
DEFAULT_REVIEW_CHANNEL = os.environ.get("EVA_SLACK_REVIEW_CHANNEL", "D0ARUK4JEDA")

APPROVE_WORDS = {"approve", "approved", "✅", ":white_check_mark:", "yes publish", "publish"}
APPROVE_REACTIONS = {"white_check_mark", "heavy_check_mark", "+1", "thumbsup"}


class SlackNotConfigured(Exception):
    """Raised when SLACK_BOT_TOKEN is absent — callers should fail safe."""


def get_token() -> str:
    return os.environ.get("SLACK_BOT_TOKEN", "").strip()


def is_configured() -> bool:
    return bool(get_token())


def _api_get(method: str, params: dict) -> dict:
    token = get_token()
    if not token:
        raise SlackNotConfigured("SLACK_BOT_TOKEN not set")
    url = f"{SLACK_API}/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_post(method: str, payload: dict) -> dict:
    token = get_token()
    if not token:
        raise SlackNotConfigured("SLACK_BOT_TOKEN not set")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{SLACK_API}/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_message(text: str, channel: str = DEFAULT_REVIEW_CHANNEL,
                 thread_ts: Optional[str] = None) -> dict:
    """Post a message. Returns {ok, ts, channel, error}."""
    payload = {"channel": channel, "text": text, "unfurl_links": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        r = _api_post("chat.postMessage", payload)
    except SlackNotConfigured as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # network / decode
        return {"ok": False, "error": f"slack post failed: {exc}"}
    return {"ok": bool(r.get("ok")), "ts": r.get("ts", ""),
            "channel": r.get("channel", channel), "error": r.get("error", "")}


def upload_image(image_path: str, channel: str = DEFAULT_REVIEW_CHANNEL,
                 title: str = "", initial_comment: str = "",
                 thread_ts: Optional[str] = None) -> dict:
    """Best-effort image upload (files.upload, multipart via requests).

    Non-fatal: if requests is missing, the file doesn't exist, or the API
    rejects it, returns ok=False and the caller keeps going with text only.
    """
    if not image_path or not os.path.exists(image_path):
        return {"ok": False, "error": f"image not found: {image_path}"}
    token = get_token()
    if not token:
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    try:
        import requests  # optional; only needed for multipart upload
    except ImportError:
        return {"ok": False, "error": "requests not available for image upload"}
    data = {"channels": channel, "title": title or os.path.basename(image_path)}
    if initial_comment:
        data["initial_comment"] = initial_comment
    if thread_ts:
        data["thread_ts"] = thread_ts
    try:
        with open(image_path, "rb") as fh:
            r = requests.post(
                f"{SLACK_API}/files.upload",
                headers={"Authorization": f"Bearer {token}"},
                data=data,
                files={"file": fh},
                timeout=30,
            )
        body = r.json()
        return {"ok": bool(body.get("ok")), "error": body.get("error", "")}
    except Exception as exc:
        return {"ok": False, "error": f"image upload failed: {exc}"}


def get_reactions(channel: str, ts: str) -> list[dict]:
    """Return the reactions on a message: [{name, users:[...]}]."""
    try:
        r = _api_get("reactions.get", {"channel": channel, "timestamp": ts})
    except Exception:
        return []
    if not r.get("ok"):
        return []
    return (r.get("message", {}) or {}).get("reactions", []) or []


def get_thread_replies(channel: str, ts: str) -> list[dict]:
    """Return replies in the thread rooted at ts (excludes the root)."""
    try:
        r = _api_get("conversations.replies", {"channel": channel, "ts": ts, "limit": "50"})
    except Exception:
        return []
    if not r.get("ok"):
        return []
    msgs = r.get("messages", []) or []
    return [m for m in msgs if m.get("ts") != ts]


def check_approval(channel: str, ts: str,
                   approver_user_id: str = DEFAULT_APPROVER_USER_ID) -> dict:
    """Has the approver approved the draft message at ``ts``?

    Approval = a ✅-family reaction by the approver, OR a threaded reply whose
    text is an approval word by the approver. Returns
    {approved: bool, via: 'reaction'|'reply'|'', reason: str}.
    """
    for reac in get_reactions(channel, ts):
        if reac.get("name") in APPROVE_REACTIONS and approver_user_id in (reac.get("users") or []):
            return {"approved": True, "via": "reaction", "reason": reac.get("name", "")}

    for msg in get_thread_replies(channel, ts):
        if msg.get("user") != approver_user_id:
            continue
        text = (msg.get("text") or "").strip().lower()
        if text in APPROVE_WORDS or text.startswith("approve"):
            return {"approved": True, "via": "reply", "reason": text[:40]}

    return {"approved": False, "via": "", "reason": ""}
