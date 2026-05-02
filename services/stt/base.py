from __future__ import annotations

from typing import Protocol, runtime_checkable

from services.audio.base import AudioClip


class TranscriptionError(RuntimeError):
    """Raised when a transcriber cannot turn audio into text."""


@runtime_checkable
class Transcriber(Protocol):
    """Speech-to-text interface used by the EVA voice loop."""

    name: str

    def transcribe(self, clip: AudioClip) -> str:
        ...
