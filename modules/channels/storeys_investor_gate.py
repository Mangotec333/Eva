"""
EVA Channels — Apollo -> GHL "Storeys Investor Outreach" approve gate.

Sibling of ``apollo_gate.py`` (Eva Acquisition PE/M&A cold outreach). Same
architecture, different ICP/pipeline/ledger — kept as a **separate module**
per standing instruction: new Storeys work must not touch the Eva
Acquisition pipeline (id ``hODxp7jDIraP6FaNZqNU``) or its GHL plumbing.

Nothing is enrolled without explicit founder approval:

  1. ``extract_and_stage(query, max_contacts)`` runs Apollo People search
     (:mod:`apollo_connector`, reused as-is with the Storeys ICP overrides
     below), drops anyone already in :mod:`storeys_investor_ledger`,
     persists the deduped batch (:mod:`storeys_investor_store`), and posts a
     review card (count + sample rows) to the founder's Slack DM.
  2. Approval arrives via ``POST /storeys/apollo/enroll/{batch_id}`` on the
     launcher, or a Slack ✅ / 'approve' reply (``check_slack_approvals``).
  3. On approval only, ``enroll(batch)`` upserts each contact through
     ``ghl_client`` (tags ``storeys-investor-lead`` + ``source:apollo-re-
     investor``), resolves the "Storeys Investor Outreach" pipeline + "New
     Lead" stage by name via ``list_pipelines()``, and files the contact
     into that pipeline stage. Each success is written to the Storeys
     ledger so it is never asked about again.
  4. Success/skip/fail counts are reported back to the Slack thread.

``enroll`` refuses to run on a batch whose status is not ``approved`` (mirrors
the Eva Acquisition gate's guarantee).

Apollo credit cost: the underlying ``apollo_connector.search_people`` call
and any future email/phone "reveal" are the only credit-consuming steps —
this gate module makes zero Apollo calls beyond what ``extract_and_stage``
triggers, and enrolment itself is GHL-only (no Apollo credits spent on
approve/reject/enroll).
"""

from __future__ import annotations

import os
import sys

_CHANNELS_DIR = os.path.dirname(os.path.abspath(__file__))
_SOCIAL_DIR = os.path.abspath(os.path.join(_CHANNELS_DIR, "..", "social-publish"))
_GHL_DIR = os.path.abspath(os.path.join(_CHANNELS_DIR, "..", "ghl-agent"))
for _p in (_CHANNELS_DIR, _SOCIAL_DIR, _GHL_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import apollo_connector                      # noqa: E402  (reused unmodified)
import storeys_investor_store as store       # noqa: E402
import storeys_investor_ledger as ledger     # noqa: E402
import slack_client                          # noqa: E402

# Task-specified GHL wiring — same Mangotec location, DIFFERENT pipeline.
GHL_LOCATION_ID = "kyK4yAY6Hur3F4deCx2n"
PIPELINE_NAME = "Storeys Investor Outreach"
STAGE_NAME = "New Lead"
LEAD_TAG = "storeys-investor-lead"           # applied on upsert
SOURCE = "apollo-re-investor"
SOURCE_TAG = f"source:{SOURCE}"

# Storeys investor ICP — RE investors / family offices / HNW allocators.
# Overrides apollo_connector's Eva-Acquisition-flavored defaults per call;
# apollo_connector.py itself is untouched.
DEFAULT_TITLES = [
    "Managing Partner",
    "General Partner",
    "Managing Director",
    "Principal",
    "Family Office Principal",
    "Chief Investment Officer",
    "Investment Director",
    "Portfolio Manager",
    "Wealth Advisor",
    "Private Investor",
]
DEFAULT_FIRM_KEYWORDS = [
    "Family Office",
    "Real Estate Private Equity",
    "Real Estate Investment",
    "Private Wealth Management",
    "RIA",
]
DEFAULT_LOCATIONS = ["United States"]

SAMPLE_ROWS = 10


def _ghl_client():
    """Build the GHL client. Live when GHL_ACCESS_TOKEN is set, else the stub."""
    import ghl_client  # noqa: PLC0415
    os.environ.setdefault("GHL_LOCATION_ID", GHL_LOCATION_ID)
    return ghl_client.build_client()


def _launcher_base() -> str:
    return os.environ.get("EVA_LAUNCHER_URL", "http://localhost:8768").rstrip("/")


def _enroll_link(batch_id: str) -> str:
    return f"{_launcher_base()}/storeys/apollo/enroll/{batch_id}"


# ---------------------------------------------------------------------------
# 1. Extract + dedup + stage for approval
# ---------------------------------------------------------------------------

def extract_and_stage(query: str = "", *,
                      max_contacts: int = apollo_connector.DEFAULT_BATCH_CAP,
                      titles: list[str] | None = None,
                      firm_keywords: list[str] | None = None,
                      locations: list[str] | None = None,
                      _search_fn=None) -> dict:
    """Extract from Apollo (Storeys ICP), dedup, stage a batch to Slack.

    No enrolment happens here — matches the Eva Acquisition gate's contract.
    """
    result = apollo_connector.extract_contacts(
        query, max_contacts=max_contacts,
        titles=titles or DEFAULT_TITLES,
        firm_keywords=firm_keywords or DEFAULT_FIRM_KEYWORDS,
        locations=locations or DEFAULT_LOCATIONS,
        _search_fn=_search_fn,
    )
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "apollo extract failed")}

    extracted = result["contacts"]
    fresh: list[dict] = []
    already: list[dict] = []
    for c in extracted:
        if ledger.is_enrolled(c.get("email", "")):
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
        f"*🏠 Storeys investor batch ready* (id `{batch_id}`)\n"
        f"Query: `{query or '(default RE investor / family office ICP)'}`\n"
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
        f"\n*To file into Storeys Investor Outreach:* reply `approve` or react "
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
    _report_to_slack(batch, f"🛑 Storeys investor batch `{batch_id}` rejected by {actor}. Not enrolled.")
    return {"ok": True, "batch": batch}


def _resolve_pipeline_stage(ghl) -> tuple[str, str, str]:
    """Find the Storeys Investor Outreach pipeline + New Lead stage id.

    Returns ``(pipeline_id, stage_id, error)`` — error is "" on success.
    """
    pipelines = ghl.list_pipelines()
    for p in pipelines:
        if p.get("name") == PIPELINE_NAME:
            for s in p.get("stages", []):
                if s.get("name") == STAGE_NAME:
                    return p.get("id", ""), s.get("id", ""), ""
            return p.get("id", ""), "", f"stage '{STAGE_NAME}' not found on pipeline"
    return "", "", f"pipeline '{PIPELINE_NAME}' not found — create it in GHL first"


def enroll(batch: dict) -> dict:
    """Enrol an *approved* batch into GHL. Refuses any other status.

    Per contact: dedup-check -> GHL upsert (lead + source tags) -> file into
    the Storeys Investor Outreach pipeline's New Lead stage -> write the
    Storeys ledger. No workflow/7-touch trigger tag — Storeys has no
    dedicated nurture workflow yet, unlike Eva Acquisition's 8024cff0.
    """
    if batch.get("status") != store.STATUS_APPROVED:
        return {"ok": False, "error": f"refusing to enrol: status={batch.get('status')}",
                "batch": batch}

    ghl = _ghl_client()
    pipeline_id, stage_id, pipe_err = _resolve_pipeline_stage(ghl)

    contacts = batch.get("contacts", [])
    success, skipped, failed = 0, 0, 0
    details: list[dict] = []

    for c in contacts:
        email = (c.get("email") or "").strip()
        if not email:
            failed += 1
            details.append({"email": "", "result": "fail", "reason": "no email"})
            continue
        if ledger.is_enrolled(email):
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
            if pipeline_id and stage_id:
                ghl.add_contact_to_pipeline(contact_id, pipeline_id, stage_id)
            elif pipe_err:
                details.append({"email": email, "result": "success_no_pipeline",
                                "ghl_contact_id": contact_id, "reason": pipe_err})
            ledger.mark_enrolled(email, SOURCE, contact_id)
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
               "total": total, "pipeline_error": pipe_err, "details": details}
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
    pipe_note = (f" ⚠️ {results['pipeline_error']}" if results.get("pipeline_error") else
                f" filed into `{PIPELINE_NAME}` / `{STAGE_NAME}`.")
    text = (
        f"*Enrol result for Storeys investor batch* `{batch['id']}`:\n"
        f"✅ enrolled: {results['success']}   "
        f"⏭️ skipped (already enrolled): {results['skipped']}   "
        f"❌ failed: {results['failed']}\n"
        f"Enrolled contacts were tagged `{LEAD_TAG}` + `{SOURCE_TAG}`,{pipe_note}"
    )
    _report_to_slack(batch, text)


__all__ = [
    "GHL_LOCATION_ID", "PIPELINE_NAME", "STAGE_NAME", "LEAD_TAG", "SOURCE",
    "SOURCE_TAG", "DEFAULT_TITLES", "DEFAULT_FIRM_KEYWORDS", "DEFAULT_LOCATIONS",
    "extract_and_stage", "approve", "reject", "enroll", "check_slack_approvals",
]
