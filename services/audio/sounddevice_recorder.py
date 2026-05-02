from __future__ import annotations

from services.audio.base import AudioClip, RecorderError


class SoundDeviceUnavailableError(RecorderError):
    """Raised when `sounddevice`/`numpy` are missing or no input device exists."""


class SoundDeviceRecorder:
    """Microphone recorder backed by the optional `sounddevice` extra.

    The `sounddevice` and `numpy` imports are deferred until `record()` runs
    so importing this module never forces the optional `[voice]` extra to be
    installed. If the extras are missing, or no microphone is available, the
    recorder raises `SoundDeviceUnavailableError` with a clear hint rather
    than silently producing empty audio.
    """

    name = "sounddevice"

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = 2

    def _load_backend(self):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as exc:
            raise SoundDeviceUnavailableError(
                "sounddevice/numpy are not installed. "
                "Install the optional voice extra: pip install -e '.[voice]'"
            ) from exc
        return sd, np

    def record(self, duration_seconds: float) -> AudioClip:
        if duration_seconds <= 0:
            raise RecorderError("duration_seconds must be > 0")

        sd, np = self._load_backend()

        try:
            recording = sd.rec(
                int(duration_seconds * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
            )
            sd.wait()
        except Exception as exc:  # sounddevice raises a hierarchy of its own errors
            raise SoundDeviceUnavailableError(
                f"Failed to capture audio from the default input device: {exc}"
            ) from exc

        buffer = np.ascontiguousarray(recording, dtype=np.int16)
        return AudioClip(
            samples=buffer.tobytes(),
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
