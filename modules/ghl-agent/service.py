"""
EVA GHL Agent — service layer (funnel build + lead-capture loop)
===============================================================

Sits between the HTTP/CLI surfaces and the GHL client, campaign copy, local
ledger, and the Eva State Ledger. Owns the module's two jobs:

- **Part 1 — one-time funnel build.** ``build_funnel()`` creates (idempotently —
  check-then-create) the "Eva Acquisition" pipeline, the "Eva Demo Call"
  calendar, the ``source`` custom field, the 7-touch templates, and the
  tag-triggered workflow. Every piece is recorded in ``funnel_artifacts`` so the
  build is idempotent across restarts and ``funnel_status()`` can answer without
  re-hitting GHL. Pieces GHL exposes only in its UI degrade to
  ``manual_required`` rather than failing the whole build.

- **Part 2 — ongoing capture loop.** ``capture_lead()`` upserts the GHL contact,
  tags it ``eva-acquisition``, drops it into the pipeline at stage "Lead", and
  enrolls it in the campaign/workflow. ``handle_webhook()`` maps inbound GHL
  events (opened, replied, booked, …) to lead lifecycle events. Both write to the
  local append-only ledger AND emit to the Eva State Ledger.

The GHL client and the state client are injected (Protocols), so the whole
service runs offline in tests with stub clients.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import campaign
import memory
from ghl_client import GHLClient, build_client
from state_client import StateLedgerClient, build_state_client

PIPELINE_NAME = "Eva Acquisition"
PIPELINE_STAGES = ["Lead", "Engaged", "Demo Booked", "Demo Held", "Closed"]
CALENDAR_NAME = "Eva Demo Call"
CUSTOM_FIELD_NAME = "source"
CUSTOM_FIELD_KEY = "contact.source"
CUSTOM_FIELD_DEFAULT = "eva-acquisition"
ACQUISITION_TAG = "eva-acquisition"

# GHL webhook event names → Eva lead lifecycle event types.
WEBHOOK_EVENT_MAP = {
    "email_opened": memory.EVENT_LEAD_ENGAGED,
    "email.opened": memory.EVENT_LEAD_ENGAGED,
    "opened": memory.EVENT_LEAD_ENGAGED,
    "email_reply": memory.EVENT_LEAD_ENGAGED,
    "reply": memory.EVENT_LEAD_ENGAGED,
    "sms_reply": memory.EVENT_LEAD_ENGAGED,
    "contact.reply": memory.EVENT_LEAD_ENGAGED,
    "touch_sent": memory.EVENT_TOUCH_SENT,
    "email_sent": memory.EVENT_TOUCH_SENT,
    "sms_sent": memory.EVENT_TOUCH_SENT,
    "call_booked": memory.EVENT_DEMO_BOOKED,
    "appointment_booked": memory.EVENT_DEMO_BOOKED,
    "appointment.booked": memory.EVENT_DEMO_BOOKED,
    "demo_booked": memory.EVENT_DEMO_BOOKED,
    "appointment_showed": memory.EVENT_DEMO_HELD,
    "demo_held": memory.EVENT_DEMO_HELD,
    "call_completed": memory.EVENT_DEMO_HELD,
    "won": memory.EVENT_CLOSED,
    "closed": memory.EVENT_CLOSED,
    "opportunity_won": memory.EVENT_CLOSED,
}


class NotFoundError(RuntimeError):
    pass


class CaptureError(RuntimeError):
    pass


class GHLAgentService:
    def __init__(self, *, db_path: str = memory.DB_PATH,
                 ghl: Optional[GHLClient] = None,
                 state: Optional[StateLedgerClient] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.ghl: GHLClient = ghl or build_client(offline=offline)
        self.state: StateLedgerClient = state or build_state_client(offline=offline)
        memory.init_db(self.db_path)

    # -----------------------------------------------------------------------
    # Part 1 — one-time funnel build (idempotent)
    # -----------------------------------------------------------------------

    def build_funnel(self) -> dict[str, Any]:
        """Create the pipeline, calendar, custom field, templates, workflow.

        Idempotent: each piece is checked against GHL (and the local artifact
        ledger) before creation. UI-only pieces return ``manual_required`` and do
        not fail the build.
        """
        created: list[dict] = []
        skipped: list[dict] = []
        manual: list[dict] = []

        def _classify(kind: str, name: str, result: dict, external_id: str = "") -> None:
            if result.get("manual_required"):
                manual.append({"kind": kind, "name": name,
                               "reason": result.get("reason", "")})
                memory.record_artifact(kind=kind, name=name, action="manual_required",
                                       detail=result, path=self.db_path)
            elif result.get("action") == "skipped":
                skipped.append({"kind": kind, "name": name, "id": external_id})
                memory.record_artifact(kind=kind, name=name, external_id=external_id,
                                       action="skipped", detail=result, path=self.db_path)
            else:
                created.append({"kind": kind, "name": name, "id": external_id})
                memory.record_artifact(kind=kind, name=name, external_id=external_id,
                                       action="created", detail=result, path=self.db_path)

        # 1. Pipeline -------------------------------------------------------
        pipeline = self._ensure_pipeline()
        _classify(memory.ARTIFACT_PIPELINE, PIPELINE_NAME, pipeline,
                  pipeline.get("id", ""))

        # 2. Calendar (book-a-call) ----------------------------------------
        calendar = self._ensure_calendar()
        booking_link = calendar.get("booking_link", "")
        _classify(memory.ARTIFACT_CALENDAR, CALENDAR_NAME, calendar,
                  calendar.get("id", ""))

        # 3. Custom field ---------------------------------------------------
        field = self._ensure_custom_field()
        _classify(memory.ARTIFACT_CUSTOM_FIELD, CUSTOM_FIELD_NAME, field,
                  field.get("id", ""))

        # 4. Templates (7-touch) -------------------------------------------
        template_ids: list[str] = []
        for touch in campaign.render_touches(booking_link):
            res = self._ensure_template(touch)
            _classify(memory.ARTIFACT_TEMPLATE, touch["name"], res, res.get("id", ""))
            if res.get("id"):
                template_ids.append(res["id"])

        # 5. Workflow (tag-triggered) --------------------------------------
        workflow = self._ensure_workflow(template_ids)
        _classify(memory.ARTIFACT_WORKFLOW, campaign.CAMPAIGN_NAME, workflow,
                  workflow.get("id", ""))

        memory.save_run("build",
                        inputs={"pipeline": PIPELINE_NAME},
                        outputs={"created": len(created), "skipped": len(skipped),
                                 "manual": len(manual)},
                        path=self.db_path)

        return {
            "pipeline": pipeline,
            "calendar": calendar,
            "booking_link": booking_link,
            "custom_field": field,
            "workflow": workflow,
            "template_count": len(template_ids),
            "created": created,
            "skipped": skipped,
            "manual_required": manual,
        }

    def _ensure_pipeline(self) -> dict:
        for p in self.ghl.list_pipelines():
            if p.get("name") == PIPELINE_NAME:
                return {**p, "action": "skipped"}
        return self.ghl.create_pipeline(PIPELINE_NAME, PIPELINE_STAGES)

    def _ensure_calendar(self) -> dict:
        for c in self.ghl.list_calendars():
            if c.get("name") == CALENDAR_NAME:
                return {**c, "action": "skipped"}
        return self.ghl.create_calendar(CALENDAR_NAME)

    def _ensure_custom_field(self) -> dict:
        for f in self.ghl.list_custom_fields():
            if f.get("field_key") == CUSTOM_FIELD_KEY or f.get("name") == CUSTOM_FIELD_NAME:
                return {**f, "action": "skipped"}
        return self.ghl.create_custom_field(CUSTOM_FIELD_NAME, CUSTOM_FIELD_KEY,
                                            CUSTOM_FIELD_DEFAULT)

    def _ensure_template(self, touch: dict) -> dict:
        for t in self.ghl.list_templates():
            if t.get("name") == touch["name"]:
                return {**t, "action": "skipped"}
        return self.ghl.create_template(
            name=touch["name"], channel=touch["channel"],
            subject=touch.get("subject", ""), body=touch["body"])

    def _ensure_workflow(self, template_ids: list[str]) -> dict:
        for w in self.ghl.list_workflows():
            if w.get("name") == campaign.CAMPAIGN_NAME:
                return {**w, "action": "skipped"}
        return self.ghl.create_workflow(campaign.CAMPAIGN_NAME, campaign.TRIGGER_TAG,
                                        template_ids)

    def funnel_status(self) -> dict[str, Any]:
        """Report which build pieces exist (from GHL + the artifact ledger)."""
        def _present(kind: str, live_names: list[str], want: str) -> dict:
            live = want in live_names
            arts = memory.list_artifacts(kind=kind, path=self.db_path)
            recorded = next((a for a in arts if a["name"] == want), None)
            return {
                "exists": bool(live or recorded),
                "in_ghl": live,
                "recorded_action": recorded["action"] if recorded else None,
                "external_id": (recorded["external_id"] if recorded else "") or "",
            }

        pipelines = [p.get("name") for p in self.ghl.list_pipelines()]
        calendars = [c.get("name") for c in self.ghl.list_calendars()]
        workflows = [w.get("name") for w in self.ghl.list_workflows()]
        template_names = [t.get("name") for t in self.ghl.list_templates()]

        templates_status = {
            t["name"]: _present(memory.ARTIFACT_TEMPLATE, template_names, t["name"])
            for t in campaign.TOUCHES
        }
        built = (
            _present(memory.ARTIFACT_PIPELINE, pipelines, PIPELINE_NAME)["exists"]
            and _present(memory.ARTIFACT_CALENDAR, calendars, CALENDAR_NAME)["exists"]
        )
        return {
            "built": built,
            "pipeline": _present(memory.ARTIFACT_PIPELINE, pipelines, PIPELINE_NAME),
            "calendar": _present(memory.ARTIFACT_CALENDAR, calendars, CALENDAR_NAME),
            "custom_field": _present(memory.ARTIFACT_CUSTOM_FIELD, [], CUSTOM_FIELD_NAME),
            "workflow": _present(memory.ARTIFACT_WORKFLOW, workflows,
                                 campaign.CAMPAIGN_NAME),
            "templates": templates_status,
        }

    # -----------------------------------------------------------------------
    # Part 2 — lead-capture loop
    # -----------------------------------------------------------------------

    def capture_lead(self, *, email: str = "", name: str = "", phone: str = "",
                     source: str = "eva-acquisition") -> dict[str, Any]:
        """Upsert contact, tag, add to pipeline at "Lead", enroll in campaign."""
        if not email and not phone:
            raise CaptureError("email or phone is required (GHL contact rule)")

        contact = self.ghl.upsert_contact(
            email=email, name=name, phone=phone,
            tags=[ACQUISITION_TAG], source=source)
        contact_id = contact.get("id", "")
        if not contact_id:
            raise CaptureError(f"contact upsert failed: {contact}")

        self.ghl.add_contact_tag(contact_id, ACQUISITION_TAG)

        # Pipeline: stage "Lead" (first stage).
        pipeline = self._ensure_pipeline()
        stage_id = self._stage_id(pipeline, "Lead")
        pipeline_id = pipeline.get("id", "")
        if pipeline_id and stage_id:
            self.ghl.add_contact_to_pipeline(contact_id, pipeline_id, stage_id)

        # Campaign enrollment via the tag-triggered workflow (if it exists).
        workflow = next((w for w in self.ghl.list_workflows()
                         if w.get("name") == campaign.CAMPAIGN_NAME), None)
        if workflow and workflow.get("id"):
            self.ghl.add_contact_to_workflow(contact_id, workflow["id"])

        # Local ledger + state ledger.
        summary = f"Lead captured: {email or phone}"
        memory.record_lead_event(
            event_type=memory.EVENT_LEAD_CAPTURED, contact_id=contact_id,
            email=email, summary=summary, source=source,
            payload={"name": name, "phone": phone, "tag": ACQUISITION_TAG},
            path=self.db_path)
        self.state.emit(event_type=memory.EVENT_LEAD_CAPTURED, summary=summary,
                        entity_id=contact_id,
                        payload={"email": email, "name": name, "source": source})

        memory.save_run("capture", inputs={"email": email},
                        outputs={"contact_id": contact_id}, path=self.db_path)

        return {"contact_id": contact_id, "status": "captured",
                "tag": ACQUISITION_TAG, "pipeline_stage": "Lead"}

    @staticmethod
    def _stage_id(pipeline: dict, stage_name: str) -> str:
        for s in pipeline.get("stages", []):
            if s.get("name") == stage_name:
                return s.get("id", "")
        return ""

    def handle_webhook(self, event: dict) -> dict[str, Any]:
        """Map an inbound GHL event to a lead lifecycle event; write both ledgers."""
        raw_type = (event.get("type") or event.get("event")
                    or event.get("event_type") or "").strip()
        event_type = WEBHOOK_EVENT_MAP.get(raw_type.lower())
        if not event_type:
            return {"ok": False, "ignored": True, "reason": f"unmapped GHL event {raw_type!r}"}

        contact_id = (event.get("contact_id") or event.get("contactId")
                      or (event.get("contact") or {}).get("id") or "")
        email = (event.get("email")
                 or (event.get("contact") or {}).get("email") or "")
        summary = event.get("summary") or f"{event_type} ({raw_type})"

        event_id = memory.record_lead_event(
            event_type=event_type, contact_id=contact_id, email=email,
            summary=summary, source="ghl-webhook", payload=event, path=self.db_path)
        state_res = self.state.emit(event_type=event_type, summary=summary,
                                    entity_id=contact_id,
                                    payload={"raw_type": raw_type, "email": email})

        memory.save_run("webhook", inputs={"raw_type": raw_type},
                        outputs={"event_type": event_type}, path=self.db_path)

        return {"ok": True, "event_type": event_type, "event_id": event_id,
                "contact_id": contact_id, "state_emit": state_res.get("ok", False)}

    # -- reads --------------------------------------------------------------
    def lead_events(self, **kwargs) -> list[dict]:
        return memory.list_lead_events(path=self.db_path, **kwargs)


__all__ = [
    "GHLAgentService",
    "NotFoundError",
    "CaptureError",
    "PIPELINE_NAME",
    "PIPELINE_STAGES",
    "CALENDAR_NAME",
    "ACQUISITION_TAG",
]
