from __future__ import annotations

from services.audio.base import AudioClip


class FakeRecorder:
    """Deterministic Recorder used by tests and offline demos.

    Returns a buffer of silence sized to the requested duration. Callers can
    pre-seed `samples` to simulate a specific clip.
    """

    name = "fake"

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        samples: bytes | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._preset = samples
        self.last_duration: float | None = None

    def record(self, duration_seconds: float) -> AudioClip:
        self.last_duration = duration_seconds
        if self._preset is not None:
            return AudioClip(
                samples=self._preset,
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=self.sample_width,
            )
        frames = max(0, int(duration_seconds * self.sample_rate))
        return AudioClip(
            samples=b"\x00" * (frames * self.sample_width * self.channels),
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
