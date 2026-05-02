from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class RecorderError(RuntimeError):
    """Raised when audio capture cannot be performed."""


@dataclass(frozen=True)
class AudioClip:
    """A captured audio buffer.

    `samples` is raw little-endian 16-bit PCM bytes, mono unless `channels`
    says otherwise. Storing PCM rather than a numpy array keeps the
    abstraction free of an optional dependency at the boundary, which lets
    tests and callers shuttle clips without importing numpy.
    """

    samples: bytes
    sample_rate: int
    channels: int = 1
    sample_width: int = 2

    @property
    def duration_seconds(self) -> float:
        frame_size = self.sample_width * self.channels
        if frame_size == 0:
            return 0.0
        frames = len(self.samples) / frame_size
        return frames / self.sample_rate if self.sample_rate else 0.0


@runtime_checkable
class Recorder(Protocol):
    """Microphone abstraction used by the EVA voice loop."""

    sample_rate: int
    channels: int

    def record(self, duration_seconds: float) -> AudioClip:
        ...
