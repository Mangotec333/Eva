from __future__ import annotations

import threading
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


class StopSignal:
    """Thread-safe flag a UI/bridge can flip to end an in-flight recording.

    The recording loop polls `is_set()` between audio chunks. This is the
    push-to-talk / chat-mic-button stop control: the caller hands a fresh
    `StopSignal` to `record_until_silence(...)` and calls `stop()` from
    any thread (signal handler, FastAPI route, GUI button) to end the
    capture early. The clip captured up to that moment is returned.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def stop(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def clear(self) -> None:
        self._event.clear()


@runtime_checkable
class Recorder(Protocol):
    """Microphone abstraction used by the EVA voice loop."""

    sample_rate: int
    channels: int

    def record(self, duration_seconds: float) -> AudioClip:
        ...


@runtime_checkable
class StoppableRecorder(Protocol):
    """Recorder that supports silence-completion and manual stop.

    Implementations capture audio in chunks, stop when a trailing silence
    window of `silence_timeout_seconds` is observed, when `max_duration_seconds`
    elapses, or when the caller flips the supplied `StopSignal`.
    """

    sample_rate: int
    channels: int

    def record_until_silence(
        self,
        *,
        silence_timeout_seconds: float,
        max_duration_seconds: float,
        threshold_rms: float,
        chunk_seconds: float = 0.1,
        stop_signal: StopSignal | None = None,
    ) -> AudioClip:
        ...
