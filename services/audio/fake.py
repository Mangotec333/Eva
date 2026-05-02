from __future__ import annotations

from collections.abc import Iterable, Iterator

from services.audio.base import AudioClip, StopSignal
from services.audio.vad import chunk_rms


class FakeRecorder:
    """Deterministic Recorder used by tests and offline demos.

    Returns a buffer of silence sized to the requested duration. Callers can
    pre-seed `samples` to simulate a specific clip, or pass `chunks=` to
    drive `record_until_silence` with a scripted chunk stream — each chunk
    represents one polling interval of the silence-detection loop.
    """

    name = "fake"

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        samples: bytes | None = None,
        chunks: Iterable[bytes] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._preset = samples
        # Preserve laziness so a generator passed by tests can fire side
        # effects (like `stop_signal.stop()`) mid-iteration. Eagerly listing
        # would defeat manual-stop tests.
        self._chunks: Iterable[bytes] | None = chunks
        self.last_duration: float | None = None
        self.last_stop_reason: str | None = None

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

    def record_until_silence(
        self,
        *,
        silence_timeout_seconds: float,
        max_duration_seconds: float,
        threshold_rms: float,
        chunk_seconds: float = 0.1,
        stop_signal: StopSignal | None = None,
    ) -> AudioClip:
        """Replay scripted chunks through the same silence/stop logic the
        real recorder uses, so tests can pin exact stop reasons.

        If `chunks=` was not provided, falls back to producing pure silence
        chunks until either `silence_timeout_seconds` of trailing silence
        elapses or `stop_signal` fires.
        """
        chunk_iter: Iterator[bytes] = (
            iter(self._chunks) if self._chunks is not None else _silence_iter(
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=self.sample_width,
                chunk_seconds=chunk_seconds,
            )
        )
        captured = bytearray()
        elapsed = 0.0
        trailing_silence = 0.0
        reason = "exhausted"
        for chunk in chunk_iter:
            if stop_signal is not None and stop_signal.is_set():
                reason = "manual_stop"
                break
            captured.extend(chunk)
            elapsed += chunk_seconds
            if chunk_rms(chunk, sample_width=self.sample_width) < threshold_rms:
                trailing_silence += chunk_seconds
            else:
                trailing_silence = 0.0
            if elapsed >= max_duration_seconds:
                reason = "max_duration"
                break
            if trailing_silence >= silence_timeout_seconds:
                reason = "silence_timeout"
                break
        else:
            # exhausted scripted chunks without hitting any stop condition
            reason = "exhausted"

        self.last_duration = elapsed
        self.last_stop_reason = reason
        return AudioClip(
            samples=bytes(captured),
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )


def _silence_iter(
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
    chunk_seconds: float,
) -> Iterator[bytes]:
    frames = max(1, int(sample_rate * chunk_seconds))
    chunk = b"\x00" * (frames * sample_width * channels)
    while True:
        yield chunk
