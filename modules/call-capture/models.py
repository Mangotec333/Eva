"""Pydantic models for the call-capture module."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ContactRef(BaseModel):
    """Who the call/meeting was with, for GHL upsert + note attach."""
    email: str = ""
    phone: str = ""
    name: str = ""

    def key(self) -> str:
        return (self.email or self.phone).lower()


class TranscriptSegment(BaseModel):
    speaker: str = "unknown"
    text: str
    start_sec: float = 0.0
    end_sec: float = 0.0


class Transcript(BaseModel):
    full_text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str = "en"
    duration_sec: float = 0.0


class CallSummary(BaseModel):
    summary: str
    action_items: list[str] = Field(default_factory=list)
    key_topics: list[str] = Field(default_factory=list)
    sentiment: str = "neutral"  # positive | neutral | negative


class CallCaptureResult(BaseModel):
    call_id: str
    contact: ContactRef
    transcript: Transcript
    call_summary: CallSummary
    ghl_contact_id: Optional[str] = None
    ghl_note_id: Optional[str] = None
    ghl_synced: bool = False
    consent_disclosed: bool = False
