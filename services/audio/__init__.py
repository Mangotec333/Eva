"""Audio recording package."""

from __future__ import annotations

from services.audio.base import AudioClip, Recorder, RecorderError
from services.audio.fake import FakeRecorder
from services.audio.sounddevice_recorder import (
    SoundDeviceRecorder,
    SoundDeviceUnavailableError,
)

RECORDER_PROVIDERS = ("sounddevice", "fake")


def build_recorder(
    provider: str,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Recorder:
    """Construct a Recorder by name.

    `sounddevice` requires the optional `[voice]` extra. If the dependency or
    the input device is unavailable the constructor raises
    `SoundDeviceUnavailableError`, which the CLI surfaces as a clear error
    instead of silently dropping audio.
    """
    if provider == "sounddevice":
        return SoundDeviceRecorder(sample_rate=sample_rate, channels=channels)
    if provider == "fake":
        return FakeRecorder(sample_rate=sample_rate, channels=channels)
    raise ValueError(f"Unknown recorder provider: {provider}")


__all__ = [
    "AudioClip",
    "Recorder",
    "RecorderError",
    "FakeRecorder",
    "SoundDeviceRecorder",
    "SoundDeviceUnavailableError",
    "RECORDER_PROVIDERS",
    "build_recorder",
]
