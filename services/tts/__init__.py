"""Text-to-speech package."""

from __future__ import annotations

from services.tts.base import Speaker
from services.tts.console import ConsoleSpeaker
from services.tts.macos_say import MacOSSaySpeaker, MacOSSaySpeakerError

TTS_PROVIDERS = ("console", "macos-say", "none")


class NullSpeaker:
    """Speaker that suppresses all output. Used by `--no-speak`."""

    name = "none"

    def speak(self, text: str) -> None:  # noqa: ARG002 - intentional no-op
        return None


def build_speaker(
    provider: str,
    *,
    voice: str | None = None,
    rate: int | None = None,
    no_speak: bool = False,
) -> Speaker:
    """Construct a Speaker by name.

    `no_speak=True` always returns a NullSpeaker regardless of `provider`,
    so callers can wire `--no-speak` through without branching.
    """
    if no_speak:
        return NullSpeaker()
    if provider == "console":
        return ConsoleSpeaker()
    if provider == "macos-say":
        return MacOSSaySpeaker(voice=voice, rate=rate)
    if provider == "none":
        return NullSpeaker()
    raise ValueError(f"Unknown TTS provider: {provider}")


__all__ = [
    "Speaker",
    "ConsoleSpeaker",
    "MacOSSaySpeaker",
    "MacOSSaySpeakerError",
    "NullSpeaker",
    "TTS_PROVIDERS",
    "build_speaker",
]
