"""
EVA Social-Publish — the approve-then-publish gate.

Flow (nothing publishes without explicit approval):

  1. ``submit_for_approval(text, image_path, platforms)`` records a draft as
     ``pending_approval`` and posts it to the founder's Slack DM with a clear
     "reply 'approve' or react ✅ to publish to LinkedIn + X" instruction plus
     an approval link (the launcher fallback endpoint).
  2. Approval arrives one of two ways:
       * ``check_slack_approvals()`` polls Slack for a ✅ reaction or 'approve'
         reply on the draft message, OR
       * the user hits ``POST /social/approve/{draft_id}`` on the launcher.
  3. On approval only, ``publish(draft)`` calls the *existing* channels
     connectors — ``linkedin_connector.post_to_linkedin`` and
     ``twitter_connector.post_tweet`` — and records the outcome back to the
     Slack thread.
  4. A draft that is never approved is never published.

Credentials are read via ``credentials.build_cfg`` (channels_config.json + env
fallback). Missing creds fail *safe*: the publish step errors to Slack rather
than silently skipping.
"""

from __future__ import annotations

import os
import sys

import credentials
import slack_client
import store

# The channels connectors live in a sibling module dir. Import them directly
# (same approach as modules/intelligence/landing_tracker.py importing ghl-agent)
# rather than re-implementing LinkedIn/X transports here.
_CHANNELS_DIR = os.path.join(os.path.dirname(__file__), "..", "channels")
if _CHANNELS_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_CHANNELS_DIR))


def _launcher_base() -> str:
    return os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768").rstrip("/")


def _approval_link(draft_id: str) -> str:
    return f"{_launcher_base()}/social/approve/{draft_id}"


def _platform_label(p: str) -> str:
    return {"x": "X (Twitter)", "twitter": "X (Twitter)", "linkedin": "LinkedIn"}.get(p, p)


# ---------------------------------------------------------------------------
# 1. Submit for approval
# ---------------------------------------------------------------------------

def submit_for_approval(text: str, image_path: str = "",
                        platforms: list[str] | None = None) -> dict:
    """Record a draft and post it to Slack for review. No publishing here."""
    platforms = platforms or ["linkedin", "x"]
    draft = store.create_draft(text=text, image_path=image_path, platforms=platforms)
    draft_id = draft["id"]

    creds = credentials.detect()
    cred_note = _credential_note(creds, platforms)

    targets = " + ".join(_platform_label(p) for p in platforms)
    review_text = (
        f"*📝 Draft ready for review* (id `{draft_id}`)\n"
        f"Targets: *{targets}*\n"
        f"{'🖼️ image attached below\n' if image_path else ''}"
        f"\n———\n{text}\n———\n\n"
        f"*To publish:* reply `approve` or react :white_check_mark: to this message, "
        f"or open {_approval_link(draft_id)}\n"
        f"A draft that is not approved is never published.\n"
        f"{cred_note}"
    )

    slack_result = slack_client.post_message(review_text, channel=slack_client.DEFAULT_REVIEW_CHANNEL)
    fields = {}
    if slack_result.get("ok"):
        fields["slack_channel"] = slack_result.get("channel", slack_client.DEFAULT_REVIEW_CHANNEL)
        fields["slack_ts"] = slack_result.get("ts", "")
        if image_path:
            slack_client.upload_image(
                image_path,
                channel=fields["slack_channel"],
                title=f"Draft {draft_id} image",
                thread_ts=fields["slack_ts"],
            )
    if fields:
        draft = store.update_draft(draft_id, fields)

    return {
        "draft": draft,
        "slack": slack_result,
        "approval_link": _approval_link(draft_id),
        "credentials": creds,
    }


def _credential_note(creds: dict, platforms: list[str]) -> str:
    warnings = []
    if any(p == "linkedin" for p in platforms) and not creds["linkedin"]["configured"]:
        warnings.append(
            f"⚠️ LinkedIn not configured — missing: {', '.join(creds['linkedin']['missing_env'])}"
        )
    if any(p in ("x", "twitter") for p in platforms) and not creds["x"]["configured"]:
        warnings.append(
            f"⚠️ X (Twitter) not configured — missing: {', '.join(creds['x']['missing_env'])}"
        )
    if not warnings:
        return ""
    return "\n" + "\n".join(warnings) + f"\n{creds['setup_hint']}"


# ---------------------------------------------------------------------------
# 2/3. Approve + publish
# ---------------------------------------------------------------------------

def approve(draft_id: str, actor: str = "launcher", via: str = "endpoint") -> dict:
    """Mark a draft approved and publish it. Idempotent for terminal states."""
    draft = store.get_draft(draft_id)
    if not draft:
        return {"ok": False, "error": f"draft {draft_id} not found"}

    if draft["status"] in (store.STATUS_PUBLISHED,):
        return {"ok": True, "noop": True, "draft": draft,
                "reason": "already published"}
    if draft["status"] == store.STATUS_REJECTED:
        return {"ok": False, "error": "draft was rejected", "draft": draft}

    draft = store.update_draft(draft_id, {
        "status": store.STATUS_APPROVED,
        "approval_actor": actor,
        "approval_via": via,
        "approved_at": store._now(),
    })
    return publish(draft)


def reject(draft_id: str, actor: str = "launcher") -> dict:
    draft = store.get_draft(draft_id)
    if not draft:
        return {"ok": False, "error": f"draft {draft_id} not found"}
    if draft["status"] == store.STATUS_PUBLISHED:
        return {"ok": False, "error": "already published — cannot reject", "draft": draft}
    draft = store.update_draft(draft_id, {"status": store.STATUS_REJECTED,
                                          "approval_actor": actor})
    _report_to_slack(draft, f"🛑 Draft `{draft_id}` rejected by {actor}. Not published.")
    return {"ok": True, "draft": draft}


def publish(draft: dict) -> dict:
    """Publish an *approved* draft to each target platform. Fails safe."""
    if draft["status"] != store.STATUS_APPROVED:
        return {"ok": False, "error": f"refusing to publish: status={draft['status']}",
                "draft": draft}

    cfg = credentials.build_cfg()
    creds = credentials.detect()
    results: dict[str, dict] = {}

    for platform in draft["platforms"]:
        if platform == "linkedin":
            results["linkedin"] = _publish_linkedin(draft["text"], cfg, creds)
        elif platform in ("x", "twitter"):
            results["x"] = _publish_x(draft["text"], cfg, creds)
        else:
            results[platform] = {"status": "error", "error": f"unknown platform {platform}"}

    ok_count = sum(1 for r in results.values() if r.get("status") == "posted")
    total = len(results)
    if ok_count == total and total > 0:
        status = store.STATUS_PUBLISHED
    elif ok_count == 0:
        status = store.STATUS_FAILED
    else:
        status = store.STATUS_PARTIAL

    draft = store.update_draft(draft["id"], {"status": status, "publish_results": results})
    _report_publish_to_slack(draft, results)
    return {"ok": status == store.STATUS_PUBLISHED, "status": status,
            "results": results, "draft": draft}


def _publish_linkedin(text: str, cfg: dict, creds: dict) -> dict:
    if not creds["linkedin"]["configured"]:
        return {"status": "not_connected",
                "error": f"LinkedIn credentials missing: {', '.join(creds['linkedin']['missing_env'])}. "
                         f"{creds['setup_hint']}"}
    try:
        from linkedin_connector import post_to_linkedin
    except Exception as exc:  # ImportError / missing requests
        return {"status": "error", "error": f"linkedin_connector unavailable: {exc}"}
    try:
        return post_to_linkedin(text, cfg)
    except Exception as exc:
        return {"status": "error", "error": f"LinkedIn publish raised: {exc}"}


def _publish_x(text: str, cfg: dict, creds: dict) -> dict:
    if not creds["x"]["configured"]:
        return {"status": "not_connected",
                "error": f"X credentials missing: {', '.join(creds['x']['missing_env'])}. "
                         f"{creds['setup_hint']}"}
    try:
        from twitter_connector import post_tweet
    except Exception as exc:  # ImportError / tweepy missing
        return {"status": "error", "error": f"twitter_connector unavailable: {exc}"}
    try:
        return post_tweet(text, cfg)
    except Exception as exc:
        return {"status": "error", "error": f"X publish raised: {exc}"}


# ---------------------------------------------------------------------------
# 2b. Poll Slack for approvals
# ---------------------------------------------------------------------------

def check_slack_approvals() -> list[dict]:
    """Scan pending drafts; approve+publish any the user approved in Slack."""
    outcomes = []
    for draft in store.list_drafts(status=store.STATUS_PENDING):
        ts = draft.get("slack_ts")
        channel = draft.get("slack_channel")
        if not ts or not channel:
            continue
        verdict = slack_client.check_approval(channel, ts)
        if verdict.get("approved"):
            outcome = approve(
                draft["id"],
                actor=slack_client.DEFAULT_APPROVER_USER_ID,
                via=f"slack:{verdict.get('via')}",
            )
            outcomes.append({"draft_id": draft["id"], **outcome})
    return outcomes


# ---------------------------------------------------------------------------
# Slack reporting
# ---------------------------------------------------------------------------

def _report_to_slack(draft: dict, text: str) -> None:
    ts = draft.get("slack_ts")
    channel = draft.get("slack_channel")
    if channel:
        slack_client.post_message(text, channel=channel, thread_ts=ts or None)


def _report_publish_to_slack(draft: dict, results: dict) -> None:
    lines = [f"*Publish result for draft* `{draft['id']}`:"]
    for platform, r in results.items():
        label = _platform_label(platform)
        if r.get("status") == "posted":
            url = r.get("url") or r.get("post_url") or ""
            lines.append(f"✅ {label}: posted {url}".rstrip())
        else:
            lines.append(f"❌ {label}: {r.get('error') or r.get('status') or 'failed'}")
    _report_to_slack(draft, "\n".join(lines))
