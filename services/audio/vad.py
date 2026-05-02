from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SilenceConfig:
    """Configuration for RMS-based silence completion.

    The defaults are tuned for a 16 kHz mono microphone in a quiet room.
    `threshold_rms` is the int16 RMS amplitude below which a chunk is
    considered silent (range 0..32767). `silence_timeout_seconds` is the
    trailing silence duration that ends the turn. `max_duration_seconds`
    is a hard cap that always stops the recording, even if speech never
    finishes — analogous to a chat-window mic auto-stop.
    """

    threshold_rms: float = 350.0
    silence_timeout_seconds: float = 1.2
    max_duration_seconds: float = 30.0
    chunk_seconds: float = 0.1


def chunk_rms(samples: bytes, sample_width: int = 2) -> float:
    """Return the RMS amplitude of an int16 PCM chunk as a float.

    Implemented in pure Python so it has no numpy/audioop dependency at
    the boundary — the voice extra is optional. Returns 0.0 for an empty
    chunk so the caller can treat empty buffers as silent.
    """
    if not samples:
        return 0.0
    if sample_width != 2:
        raise ValueError("chunk_rms only supports 16-bit PCM samples")
    if len(samples) % 2 != 0:
        # truncate trailing odd byte rather than crash on a short read
        samples = samples[: len(samples) - 1]
    total = 0
    count = len(samples) // 2
    if count == 0:
        return 0.0
    # int.from_bytes per-frame is fast enough for ~100ms chunks at 16kHz
    # (1600 frames) and keeps the dependency surface minimal.
    for i in range(0, len(samples), 2):
        sample = int.from_bytes(samples[i : i + 2], "little", signed=True)
        total += sample * sample
    return math.sqrt(total / count)


def is_silent(samples: bytes, threshold_rms: float, sample_width: int = 2) -> bool:
    return chunk_rms(samples, sample_width=sample_width) < threshold_rms
