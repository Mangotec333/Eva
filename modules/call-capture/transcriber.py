"""
Call-capture — transcription client (behind a Protocol)
=========================================================

Same pattern as ``ghl-agent/ghl_client.py``: a Protocol so the pipeline and
tests never depend on the network, a real HTTP implementation, and an
offline stub.

- ``HttpWhisperClient`` — calls OpenAI's Whisper transcription endpoint
  (``POST /v1/audio/transcriptions``) via ``httpx``. Auth is a
  ``WHISPER_API_KEY`` / ``OPENAI_API_KEY`` env var, injected the same way
  other Eva modules pull secrets (custom-credentials proxy in the sandbox,
  plain env var in production).
- ``StubTranscriberClient`` — deterministic, network-free. Used by tests and
  local dev. Returns a canned transcript unless a fixture is provided.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, runtime_checkable

from models import Transcript, TranscriptSegment

logger = logging.getLogger("eva.call_capture.transcriber")

WHISPER_API_BASE = "https://api.openai.com/v1"


@runtime_checkable
class TranscriberClient(Protocol):
    def transcribe(self, audio_path: str) -> Transcript: ...


class TranscriberError(RuntimeError):
    pass


class StubTranscriberClient:
    """Offline client — tests and sandbox. No network, fully deterministic."""

    def __init__(self, fixture_text: str = "") -> None:
        self.fixture_text = fixture_text or (
            "Hi, thanks for taking my call. I wanted to follow up on the "
            "Mission Villa numbers and see if a seller-carry structure could "
            "work for both of us. I can put two hundred fifty thousand down "
            "today. Let's set up a call next week to go through the details."
        )
        self.calls: list[str] = []

    def transcribe(self, audio_path: str) -> Transcript:
        self.calls.append(audio_path)
        return Transcript(
            full_text=self.fixture_text,
            segments=[
                TranscriptSegment(speaker="caller", text=self.fixture_text,
                                  start_sec=0.0, end_sec=12.0),
            ],
            language="en",
            duration_sec=12.0,
        )


class HttpWhisperClient:
    """Real client — OpenAI Whisper transcription API."""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: str = WHISPER_API_BASE,
                 model: str = "whisper-1") -> None:
        self.api_key = api_key or os.environ.get("WHISPER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.model = model
        if not self.api_key:
            logger.warning("HttpWhisperClient created with no API key — calls will fail")
        try:
            import httpx  # noqa: F401
            self._httpx_available = True
        except ImportError:
            self._httpx_available = False

    def transcribe(self, audio_path: str) -> Transcript:
        if not self.api_key:
            raise TranscriberError("No WHISPER_API_KEY/OPENAI_API_KEY configured")
        if not self._httpx_available:
            raise TranscriberError("httpx not installed — cannot make live transcription calls")

        import httpx

        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "application/octet-stream")}
            data = {"model": self.model, "response_format": "verbose_json"}
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = httpx.post(f"{self.base_url}/audio/transcriptions",
                              headers=headers, data=data, files=files, timeout=120.0)
        if resp.status_code >= 400:
            raise TranscriberError(f"Whisper API {resp.status_code}: {resp.text[:300]}")

        payload = resp.json()
        segments = [
            TranscriptSegment(
                speaker="unknown",
                text=seg.get("text", "").strip(),
                start_sec=seg.get("start", 0.0),
                end_sec=seg.get("end", 0.0),
            )
            for seg in payload.get("segments", [])
        ]
        return Transcript(
            full_text=payload.get("text", "").strip(),
            segments=segments,
            language=payload.get("language", "en"),
            duration_sec=payload.get("duration", 0.0),
        )


def build_transcriber_client(*, use_stub: Optional[bool] = None) -> TranscriberClient:
    """Factory mirroring ghl-agent's build pattern — stub unless a real key is set."""
    if use_stub is None:
        use_stub = not bool(os.environ.get("WHISPER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    if use_stub:
        return StubTranscriberClient()
    return HttpWhisperClient()
