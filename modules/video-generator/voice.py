"""
EVA Video Generator — voiceover synthesis (behind a Protocol).

Mirrors the Speaker Protocol pattern in ``services/tts``: a ``VoiceSynth``
Protocol with a deterministic offline ``StubVoiceSynth`` (used in tests) and a
real ``MacOSSayVoiceSynth`` that shells out to macOS ``say`` then converts to
WAV with ffmpeg. The real impl is darwin-guarded exactly like ``MacOSSaySpeaker``
(clear error off-darwin, opt-in ``fallback_to_print``-style stub fallback).

A paid TTS / AI-video voice API can later be wired behind this same Protocol
without touching callers — no paid dependency is added now.
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import sys
import wave
from typing import Optional, Protocol, runtime_checkable

SAMPLE_RATE = 22050
# Rough narration pace used to size stub audio so scene durations are realistic.
_WORDS_PER_SEC = 2.6
_MIN_SECONDS = 1.2


@runtime_checkable
class VoiceSynth(Protocol):
    """Synthesize speech for ``text`` to a WAV file. Returns the WAV path."""

    def synth(self, text: str, out_wav_path: str) -> str:
        ...


class VoiceSynthError(RuntimeError):
    """Raised when a voice synthesizer cannot be used or invoked."""


def estimate_seconds(text: str) -> float:
    words = max(len(text.split()), 1)
    return max(_MIN_SECONDS, round(words / _WORDS_PER_SEC, 2))


class StubVoiceSynth:
    """Offline synth — writes a deterministic short tone WAV via stdlib ``wave``.

    No ffmpeg, no network. Duration is a function of the text length so scene
    timing in tests matches what real narration would roughly produce.
    """

    name = "stub"

    def __init__(self, tone_hz: float = 220.0) -> None:
        self.tone_hz = tone_hz

    def synth(self, text: str, out_wav_path: str) -> str:
        seconds = estimate_seconds(text)
        n_frames = int(SAMPLE_RATE * seconds)
        os.makedirs(os.path.dirname(os.path.abspath(out_wav_path)), exist_ok=True)
        with wave.open(out_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            frames = bytearray()
            # Low-amplitude tone with a gentle fade so it is a real, quiet track.
            amp = 0.06 * 32767
            for i in range(n_frames):
                val = amp * math.sin(2 * math.pi * self.tone_hz * (i / SAMPLE_RATE))
                frames += struct.pack("<h", int(val))
            wf.writeframes(bytes(frames))
        return out_wav_path


class MacOSSayVoiceSynth:
    """Real synth — macOS ``say -o file.aiff`` then ffmpeg-convert to WAV.

    Darwin-only, guarded like ``services/tts/macos_say.MacOSSaySpeaker``: raises
    ``VoiceSynthError`` off-darwin or when ``say``/ffmpeg is missing, unless
    ``fallback_to_stub`` is set (opt-in, so silent drops never happen).
    """

    name = "macos-say"

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        *,
        say_path: Optional[str] = None,
        ffmpeg_path: str = "ffmpeg",
        fallback_to_stub: bool = False,
        platform: Optional[str] = None,
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.ffmpeg_path = ffmpeg_path
        self.fallback_to_stub = fallback_to_stub
        self._platform = platform if platform is not None else sys.platform
        self._say_path = say_path or ("/usr/bin/say" if self._platform == "darwin" else None)

    def _ensure_available(self) -> str:
        if self._platform != "darwin":
            raise VoiceSynthError(
                f"macOS `say` voice is only available on darwin "
                f"(current platform: {self._platform})."
            )
        if not self._say_path:
            raise VoiceSynthError("Could not locate the `say` executable.")
        return self._say_path

    def synth(self, text: str, out_wav_path: str) -> str:
        try:
            say_path = self._ensure_available()
        except VoiceSynthError:
            if self.fallback_to_stub:
                return StubVoiceSynth().synth(text, out_wav_path)
            raise

        os.makedirs(os.path.dirname(os.path.abspath(out_wav_path)), exist_ok=True)
        aiff = out_wav_path + ".aiff"
        cmd = [say_path]
        if self.voice:
            cmd += ["-v", self.voice]
        if self.rate is not None:
            cmd += ["-r", str(self.rate)]
        cmd += ["-o", aiff, "--", text]
        try:
            subprocess.run(cmd, check=True)
            subprocess.run(
                [self.ffmpeg_path, "-y", "-i", aiff,
                 "-ar", str(SAMPLE_RATE), "-ac", "1", out_wav_path],
                check=True,
            )
        except FileNotFoundError as exc:
            raise VoiceSynthError(f"`say`/ffmpeg not found: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise VoiceSynthError(f"voice synth failed (exit {exc.returncode})") from exc
        finally:
            if os.path.exists(aiff):
                os.remove(aiff)
        return out_wav_path


def wav_duration_seconds(path: str) -> float:
    with wave.open(path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or SAMPLE_RATE
    return frames / float(rate)


def build_voice(stub: bool = False, **kwargs) -> VoiceSynth:
    if stub:
        return StubVoiceSynth()
    return MacOSSayVoiceSynth(**kwargs)


__all__ = [
    "VoiceSynth",
    "VoiceSynthError",
    "StubVoiceSynth",
    "MacOSSayVoiceSynth",
    "build_voice",
    "wav_duration_seconds",
    "estimate_seconds",
    "SAMPLE_RATE",
]
