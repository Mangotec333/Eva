from __future__ import annotations

import time

from services.audio.base import AudioClip, RecorderError, StopSignal
from services.audio.vad import chunk_rms


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
        self.last_stop_reason: str | None = None

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

    def record_until_silence(
        self,
        *,
        silence_timeout_seconds: float,
        max_duration_seconds: float,
        threshold_rms: float,
        chunk_seconds: float = 0.1,
        stop_signal: StopSignal | None = None,
    ) -> AudioClip:
        """Capture chunks until trailing silence, hard cap, or manual stop.

        Uses an `InputStream` so we can poll a stop signal between reads —
        `sd.rec` blocks for a fixed duration and would defeat both the
        silence-completion and the chat-mic-button stop semantics.
        """
        if max_duration_seconds <= 0:
            raise RecorderError("max_duration_seconds must be > 0")
        if chunk_seconds <= 0:
            raise RecorderError("chunk_seconds must be > 0")

        sd, np = self._load_backend()
        frames_per_chunk = max(1, int(self.sample_rate * chunk_seconds))
        captured = bytearray()
        trailing_silence = 0.0
        elapsed = 0.0
        reason = "max_duration"

        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=frames_per_chunk,
            )
        except Exception as exc:
            raise SoundDeviceUnavailableError(
                f"Failed to open default input stream: {exc}"
            ) from exc

        with stream:
            while elapsed < max_duration_seconds:
                if stop_signal is not None and stop_signal.is_set():
                    reason = "manual_stop"
                    break
                try:
                    block, _overflowed = stream.read(frames_per_chunk)
                except Exception as exc:
                    raise SoundDeviceUnavailableError(
                        f"Audio read failed mid-capture: {exc}"
                    ) from exc
                buf = np.ascontiguousarray(block, dtype=np.int16).tobytes()
                captured.extend(buf)
                elapsed += chunk_seconds
                if chunk_rms(buf, sample_width=self.sample_width) < threshold_rms:
                    trailing_silence += chunk_seconds
                    if trailing_silence >= silence_timeout_seconds:
                        reason = "silence_timeout"
                        break
                else:
                    trailing_silence = 0.0
                # tiny yield so the stop signal can be observed promptly even
                # if the stream is producing back-to-back blocks
                time.sleep(0)

        self.last_stop_reason = reason
        return AudioClip(
            samples=bytes(captured),
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
