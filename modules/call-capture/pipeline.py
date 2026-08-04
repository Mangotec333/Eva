"""
Call-capture pipeline: audio -> transcript -> summary -> GHL sync.

Mirrors ghl-agent's client-injection style so tests run fully offline with
stubs, and production wires in the real Whisper + LLM + GHL clients.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ghl-agent"))

from ghl_client import GHLClient  # noqa: E402
from models import CallCaptureResult, ContactRef  # noqa: E402
from summarizer import SummarizerClient  # noqa: E402
from transcriber import TranscriberClient  # noqa: E402

logger = logging.getLogger("eva.call_capture.pipeline")

CALL_TAG = "eva-call-captured"


def format_ghl_note(result_summary, transcript_full_text: str, consent_disclosed: bool) -> str:
    """Human-readable CRM note body — what a rep sees on the contact record."""
    consent_line = (
        "Consent disclosed to all parties."
        if consent_disclosed
        else "⚠ Consent NOT confirmed — verify before reuse (CA is a two-party consent state)."
    )
    action_items = "\n".join(f"- {a}" for a in result_summary.action_items) or "- (none)"
    topics = ", ".join(result_summary.key_topics) or "n/a"
    return (
        f"[Eva Call Capture] Sentiment: {result_summary.sentiment}\n"
        f"{consent_line}\n\n"
        f"Summary:\n{result_summary.summary}\n\n"
        f"Action items:\n{action_items}\n\n"
        f"Topics: {topics}\n\n"
        f"--- Full transcript ---\n{transcript_full_text}"
    )


class CallCapturePipeline:
    def __init__(self, *, transcriber: TranscriberClient,
                 summarizer: SummarizerClient, ghl: GHLClient) -> None:
        self.transcriber = transcriber
        self.summarizer = summarizer
        self.ghl = ghl

    def run(self, *, audio_path: str, contact: ContactRef,
            consent_disclosed: bool, sync_to_ghl: bool = True) -> CallCaptureResult:
        call_id = f"call_{uuid.uuid4().hex[:10]}"
        logger.info("call_capture_started", extra={"call_id": call_id})

        transcript = self.transcriber.transcribe(audio_path)
        call_summary = self.summarizer.summarize(transcript)

        result = CallCaptureResult(
            call_id=call_id,
            contact=contact,
            transcript=transcript,
            call_summary=call_summary,
            consent_disclosed=consent_disclosed,
        )

        if not sync_to_ghl:
            return result

        contact_res = self.ghl.upsert_contact(
            email=contact.email, name=contact.name, phone=contact.phone,
            tags=[CALL_TAG], source="eva-call-capture",
        )
        ghl_contact_id = contact_res.get("id")
        result.ghl_contact_id = ghl_contact_id

        if ghl_contact_id:
            self.ghl.add_contact_tag(ghl_contact_id, CALL_TAG)
            note_body = format_ghl_note(call_summary, transcript.full_text, consent_disclosed)
            note_res = self.ghl.add_contact_note(ghl_contact_id, note_body)
            result.ghl_note_id = note_res.get("id")
            result.ghl_synced = bool(note_res.get("ok", False))
        else:
            logger.warning("call_capture_ghl_upsert_failed", extra={"call_id": call_id})

        logger.info("call_capture_completed", extra={
            "call_id": call_id, "ghl_synced": result.ghl_synced,
        })
        return result
