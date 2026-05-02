"""Speech-to-text package."""

from __future__ import annotations

from services.stt.base import Transcriber, TranscriptionError
from services.stt.text_provider import TextTranscriber
from services.stt.whisper_cpp import WhisperCppTranscriber, WhisperCppUnavailableError

STT_PROVIDERS = ("text", "whisper-cpp")


def build_transcriber(
    provider: str,
    *,
    whisper_bin: str | None = None,
    whisper_model: str | None = None,
    fixed_text: str | None = None,
) -> Transcriber:
    """Construct a Transcriber by name.

    `text` is the offline mock used by tests — it returns `fixed_text` (or
    a placeholder) regardless of audio content. `whisper-cpp` shells out to
    a user-supplied whisper.cpp binary and model. Both binary and model
    paths are required at construction time so misconfiguration fails loudly
    rather than at the first transcription.
    """
    if provider == "text":
        return TextTranscriber(fixed_text=fixed_text or "hello eva")
    if provider == "whisper-cpp":
        if not whisper_bin or not whisper_model:
            raise ValueError(
                "whisper-cpp provider requires --whisper-bin and --whisper-model"
            )
        return WhisperCppTranscriber(binary=whisper_bin, model=whisper_model)
    raise ValueError(f"Unknown STT provider: {provider}")


__all__ = [
    "Transcriber",
    "TranscriptionError",
    "TextTranscriber",
    "WhisperCppTranscriber",
    "WhisperCppUnavailableError",
    "STT_PROVIDERS",
    "build_transcriber",
]
