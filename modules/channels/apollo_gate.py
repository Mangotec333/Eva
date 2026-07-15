"""
EVA Channels — Apollo→GHL cold-outreach approve gate.

Nothing is enrolled without explicit founder approval. The flow reuses the
social-publish approve-gate pattern and the existing Slack + GHL clients:

  1. ``extract_and_stage(query, max_contacts)`` runs Apollo People search
     (:mod:`apollo_connector`), drops anyone already in the
     :mod:`enrolled_contacts` ledger, persists the deduped batch
     (:mod:`apollo_store`), and posts a review card (count + 10 sample rows) to
     the founder's Slack DM (D0ARUK4JEDA by default).
  2. Approval arrives one of two ways:
       * ``check_slack_approvals()`` polls Slack for a ✅ reaction or 'approve'
         reply on the batch card (via ``slack_client.check_approval``), OR
       * the founder hits ``POST /apollo/enroll/{batch_id}`` on the launcher.
  3. On approval only, ``enroll(batch)`` upserts each contact through
     ``ghl_client`` (tags ``eva-acquisition-lead`` + ``source:apollo-pe-ma``),
     then tags ``eva-acquisition`` which fires GHL workflow 8024cff0 (the
     7-touch). Each success is written to the enrolled ledger so it is never
     asked about again.
  4. Success/skip/fail counts are reported back to the Slack thread.

``enroll`` refuses to run on a batch whose status is not ``approved`` — that is
the "refuse enrol pre-approval" guarantee (mirrors social gate's ``publish``).
"""

from __future__ import annotations

import os
import sys

# slack_client lives in the social-publish module dir; the GHL client lives in
# ghl-agent. Both are put on sys.path so we REUSE them rather than
# re-implementing the Slack / LeadConnector transports here (same approach the
# social gate uses to reach the channels connectors).
_SOCIAL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "social-publish"))
_GHL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ghl-agent"))
for _p in (_SOCIAL_DIR, _GHL_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import apollo_connector
import apollo_store as store
import enrolled_contacts
import slack_client

# Task-specified GHL wiring.
GHL_LOCATION_ID = "kyK4yAY6Hur3F4deCx2n"
LEAD_TAG = "eva-acquisition-lead"          # applied on upsert
TRIGGER_TAG = "eva-acquisition"            # fires 7-touch workflow 8024cff0
WORKFLOW_ID = "8024cff0"
SOURCE = "apollo-pe-ma"
SOURCE_TAG = f"source:{SOURCE}"

SAMPLE_ROWS = 10


def _ghl_client():
    """Build the GHL client. Live when GHL_ACCESS_TOKEN is set, else the stub."""
    import ghl_client  # noqa: PLC0415
    # Pin the acquisition location for the live client unless already set.
    os.environ.setdefault("GHL_LOCATION_ID", GHL_LOCATION_ID)
    return ghl_client.build_client()


def _launcher_base() -> str:
    return os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768").rstrip("/")


def _enroll_link(batch_id: str) -> str:
    return f"{_launcher_base()}/apollo/enroll/{batch_id}"


# ---------------------------------------------------------------------------
# 1. Extract + dedup + stage for approval
# ---------------------------------------------------------------------------

def extract_and_stage(query: str = "", *, max_contacts: int = apollo_connector.DEFAULT_BATCH_CAP,
                      _search_fn=None) -> dict:
    """Extract from Apollo, dedup against the ledger, stage a batch to Slack.

    ``_search_fn`` is forwarded to :func:`apollo_connector.extract_contacts` for
    offline testing. No enrolment happens here.
    """
    result = apollo_connector.extract_contacts(
        query, max_contacts=max_contacts, _search_fn=_search_fn)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "apollo extract failed")}

    extracted = result["contacts"]
    fresh: list[dict] = []
    already: list[dict] = []
    for c in extracted:
        if enrolled_contacts.is_enrolled(c.get("email", "")):
            already.append(c)
        else:
            fresh.append(c)

    batch = store.create_batch(fresh, query=query, source=SOURCE)
    batch_id = batch["id"]

    review_text = _review_card(batch_id, fresh, len(already), query)
    slack_result = slack_client.post_message(
        review_text, channel=slack_client.DEFAULT_REVIEW_CHANNEL)
    fields = {}
    if slack_result.get("ok"):
        fields["slack_channel"] = slack_result.get("channel", slack_client.DEFAULT_REVIEW_CHANNEL)
        fields["slack_ts"] = slack_result.get("ts", "")
    if fields:
        batch = store.update_batch(batch_id, fields)

    return {
        "ok": True,
        "batch": batch,
        "extracted": len(extracted),
        "deduped_out": len(already),
        "staged": len(fresh),
        "slack": slack_result,
        "enroll_link": _enroll_link(batch_id),
    }


def _review_card(batch_id: str, contacts: list[dict], deduped: int,
                 query: str) -> str:
    header = (
        f"*📇 Apollo cold-outreach batch ready* (id `{batch_id}`)\n"
        f"Query: `{query or '(default PE/M&A ICP)'}`\n"
        f"*{len(contacts)}* new contacts staged"
        f"{f' · {deduped} skipped (already enrolled)' if deduped else ''}\n"
    )
    if contacts:
        lines = ["```", "name | title | company | email"]
        for c in contacts[:SAMPLE_ROWS]:
            lines.append(
                f"{c.get('name','') or '—'} | {c.get('title','') or '—'} | "
                f"{c.get('company','') or '—'} | {c.get('email','') or '—'}")
        if len(contacts) > SAMPLE_ROWS:
            lines.append(f"... +{len(contacts) - SAMPLE_ROWS} more")
        lines.append("```")
        sample = "\n".join(lines)
    else:
        sample = "_No new contacts to enrol (all were already enrolled)._"
    footer = (
        f"\n*To enrol into the 7-touch:* reply `approve` or react "
        f":white_check_mark: to this message, or open {_enroll_link(batch_id)}\n"
        f"A batch that is not approved is never enrolled."
    )
    return header + sample + footer


# ---------------------------------------------------------------------------
# 2/3. Approve + enroll
# ---------------------------------------------------------------------------

def approve(batch_id: str, actor: str = "launcher", via: str = "endpoint") -> dict:
    """Mark a batch approved and enrol it. Idempotent for terminal states."""
    batch = store.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": f"batch {batch_id} not found"}
    if batch["status"] == store.STATUS_ENROLLED:
        return {"ok": True, "noop": True, "batch": batch, "reason": "already enrolled"}
    if batch["status"] == store.STATUS_REJECTED:
        return {"ok": False, "error": "batch was rejected", "batch": batch}

    batch = store.update_batch(batch_id, {
        "status": store.STATUS_APPROVED,
        "approval_actor": actor,
        "approval_via": via,
        "approved_at": store._now(),
    })
    return enroll(batch)


def reject(batch_id: str, actor: str = "launcher") -> dict:
    batch = store.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": f"batch {batch_id} not found"}
    if batch["status"] == store.STATUS_ENROLLED:
        return {"ok": False, "error": "already enrolled — cannot reject", "batch": batch}
    batch = store.update_batch(batch_id, {"status": store.STATUS_REJECTED,
                                          "approval_actor": actor})
    _report_to_slack(batch, f"🛑 Apollo batch `{batch_id}` rejected by {actor}. Not enrolled.")
    return {"ok": True, "batch": batch}


def enroll(batch: dict) -> dict:
    """Enrol an *approved* batch into GHL. Refuses any other status.

    Per contact: dedup-check → GHL upsert (lead + source tags) → tag
    ``eva-acquisition`` (fires the 7-touch) → write the enrolled ledger.
    """
    if batch.get("status") != store.STATUS_APPROVED:
        return {"ok": False, "error": f"refusing to enrol: status={batch.get('status')}",
                "batch": batch}

    ghl = _ghl_client()
    contacts = batch.get("contacts", [])
    success, skipped, failed = 0, 0, 0
    details: list[dict] = []

    for c in contacts:
        email = (c.get("email") or "").strip()
        if not email:
            failed += 1
            details.append({"email": "", "result": "fail", "reason": "no email"})
            continue
        if enrolled_contacts.is_enrolled(email):
            skipped += 1
            details.append({"email": email, "result": "skip", "reason": "already enrolled"})
            continue
        try:
            up = ghl.upsert_contact(
                email=email, name=c.get("name", ""), phone=c.get("phone", ""),
                tags=[LEAD_TAG, SOURCE_TAG], source=SOURCE)
            contact_id = up.get("id", "")
            if not contact_id or up.get("ok") is False:
                failed += 1
                details.append({"email": email, "result": "fail",
                                "reason": f"upsert failed: {up.get('error') or up}"})
                continue
            # Trigger tag fires GHL workflow 8024cff0 (the 7-touch sequence).
            ghl.add_contact_tag(contact_id, TRIGGER_TAG)
            enrolled_contacts.mark_enrolled(email, SOURCE, contact_id)
            success += 1
            details.append({"email": email, "result": "success", "ghl_contact_id": contact_id})
        except Exception as exc:
            failed += 1
            details.append({"email": email, "result": "fail", "reason": str(exc)})

    total = len(contacts)
    if success == total and total > 0:
        status = store.STATUS_ENROLLED
    elif success == 0:
        status = store.STATUS_FAILED if total else store.STATUS_ENROLLED
    else:
        status = store.STATUS_PARTIAL

    results = {"success": success, "skipped": skipped, "failed": failed,
               "total": total, "details": details}
    batch = store.update_batch(batch["id"], {"status": status, "enroll_results": results})
    _report_enroll_to_slack(batch, results)
    return {"ok": success > 0 or total == 0, "status": status,
            "results": results, "batch": batch}


# ---------------------------------------------------------------------------
# 2b. Poll Slack for approvals
# ---------------------------------------------------------------------------

def check_slack_approvals() -> list[dict]:
    """Scan pending batches; enrol any the founder approved in Slack."""
    outcomes = []
    for batch in store.list_batches(status=store.STATUS_PENDING):
        ts = batch.get("slack_ts")
        channel = batch.get("slack_channel")
        if not ts or not channel:
            continue
        verdict = slack_client.check_approval(channel, ts)
        if verdict.get("approved"):
            outcome = approve(batch["id"],
                              actor=slack_client.DEFAULT_APPROVER_USER_ID,
                              via=f"slack:{verdict.get('via')}")
            outcomes.append({"batch_id": batch["id"], **outcome})
    return outcomes


# ---------------------------------------------------------------------------
# Slack reporting
# ---------------------------------------------------------------------------

def _report_to_slack(batch: dict, text: str) -> None:
    ts = batch.get("slack_ts")
    channel = batch.get("slack_channel")
    if channel:
        slack_client.post_message(text, channel=channel, thread_ts=ts or None)


def _report_enroll_to_slack(batch: dict, results: dict) -> None:
    text = (
        f"*Enrol result for Apollo batch* `{batch['id']}`:\n"
        f"✅ enrolled: {results['success']}   "
        f"⏭️ skipped (already enrolled): {results['skipped']}   "
        f"❌ failed: {results['failed']}\n"
        f"Enrolled contacts were tagged `{LEAD_TAG}` + `{SOURCE_TAG}` and "
        f"`{TRIGGER_TAG}` (fires the 7-touch)."
    )
    _report_to_slack(batch, text)


__all__ = [
    "GHL_LOCATION_ID", "LEAD_TAG", "TRIGGER_TAG", "WORKFLOW_ID", "SOURCE",
    "SOURCE_TAG", "extract_and_stage", "approve", "reject", "enroll",
    "check_slack_approvals",
]
