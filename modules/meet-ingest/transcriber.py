"""
EVA Meet Ingest — local transcription transport.

Extracts audio from a downloaded recording with ffmpeg (preinstalled; 16kHz mono
WAV) and transcribes it locally with the repo's shared
``services/stt/whisper_cpp.py`` (``WhisperCppTranscriber`` — shells out to a
user-built whisper.cpp binary + ggml model, no network). ``services/`` is a
shared library, not a sibling module, so importing it is allowed by the
Architecture Directive.

Per rules #3/#7 the transport sits behind a small ``Transcriber`` Protocol with
a ``StubTranscriber`` (offline, canned text — used in tests, no ffmpeg/whisper
needed) and a ``WhisperTranscriber`` (the real ffmpeg + whisper.cpp pipeline).
The real transcriber never fakes success: a missing binary/model surfaces as a
clear error.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave
from typing import Optional, Protocol, runtime_checkable

# Ensure the EVA repo root is importable so ``services.*`` (shared libs) resolve
# whether this module is run flat (cwd = module dir) or from the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# whisper.cpp prerequisites are user-provided; point EVA at them via env.
WHISPER_BIN = os.environ.get("EVA_WHISPER_BIN", os.path.expanduser("~/.eva/whisper/main"))
WHISPER_MODEL = os.environ.get(
    "EVA_WHISPER_MODEL", os.path.expanduser("~/.eva/whisper/ggml-base.en.bin")
)


class TranscriptionError(RuntimeError):
    """Raised when audio extraction or transcription cannot be performed."""


@runtime_checkable
class Transcriber(Protocol):
    """Transcription interface. Implementations must not fake success; an
    unavailable backend raises ``TranscriptionError`` with a clear message."""

    name: str

    def transcribe(self, video_path: str) -> str: ...


# ---------------------------------------------------------------------------
# Stub (offline, canned) — used in tests. No ffmpeg, no whisper.cpp.
# ---------------------------------------------------------------------------

class StubTranscriber:
    """Offline transcriber returning canned transcript text. No subprocess."""

    name = "stub"

    def __init__(self, text: Optional[str] = None):
        self.text = text if text is not None else (
            "This is a stub transcript. Attendees discussed the weekly roadmap, "
            "the fundraise timeline, and next steps for the EVA modules."
        )

    def transcribe(self, video_path: str) -> str:
        return self.text


# ---------------------------------------------------------------------------
# Real (ffmpeg + whisper.cpp) — the local, zero-API-cost pipeline.
# ---------------------------------------------------------------------------

def extract_audio_wav(video_path: str, wav_path: str) -> str:
    """Extract 16kHz mono 16-bit PCM WAV from a video/audio file via ffmpeg.

    16kHz mono is the format whisper.cpp expects. ffmpeg is preinstalled on the
    Eva host; a missing binary surfaces as a clear ``TranscriptionError``.
    """
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-ac", "1",            # mono
        "-ar", "16000",        # 16 kHz
        "-acodec", "pcm_s16le",  # 16-bit PCM
        wav_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise TranscriptionError(
            "ffmpeg not found. It is expected to be preinstalled on the Eva host."
        ) from exc
    if proc.returncode != 0:
        raise TranscriptionError(
            f"ffmpeg failed to extract audio (status {proc.returncode}): "
            f"{(proc.stderr or '').strip()[-500:]}"
        )
    return wav_path


def _load_wav_clip(wav_path: str):
    """Read a WAV file into an ``AudioClip`` for WhisperCppTranscriber."""
    from services.audio.base import AudioClip

    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    return AudioClip(
        samples=frames,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )


class WhisperTranscriber:
    """ffmpeg audio extraction + local whisper.cpp transcription.

    Wraps the shared ``WhisperCppTranscriber``; the whisper.cpp binary + model
    are user-provided prerequisites (see setup.sh / README). The binary/model
    are verified lazily on first ``transcribe`` so this class can be constructed
    (and its config inspected) without the prerequisites present.
    """

    name = "whisper-cpp"

    def __init__(
        self,
        binary: str = WHISPER_BIN,
        model: str = WHISPER_MODEL,
        *,
        language: Optional[str] = None,
        threads: Optional[int] = None,
    ):
        self.binary = binary
        self.model = model
        self.language = language
        self.threads = threads
        self._backend = None

    def _get_backend(self):
        if self._backend is not None:
            return self._backend
        try:
            from services.stt.whisper_cpp import (
                WhisperCppTranscriber,
                WhisperCppUnavailableError,
            )
        except ImportError as exc:
            raise TranscriptionError(
                "Could not import services.stt.whisper_cpp — ensure the module is "
                "run from within the EVA repo so 'services' is on sys.path."
            ) from exc
        try:
            self._backend = WhisperCppTranscriber(
                self.binary,
                self.model,
                language=self.language,
                threads=self.threads,
            )
        except WhisperCppUnavailableError as exc:
            raise TranscriptionError(str(exc)) from exc
        return self._backend

    def transcribe(self, video_path: str) -> str:
        if not os.path.exists(video_path):
            raise TranscriptionError(f"recording not found at {video_path}")
        backend = self._get_backend()
        with tempfile.TemporaryDirectory(prefix="eva-meet-") as tmp:
            wav_path = os.path.join(tmp, "audio.wav")
            extract_audio_wav(video_path, wav_path)
            clip = _load_wav_clip(wav_path)
            return backend.transcribe(clip)


def build_transcriber(name: Optional[str] = None) -> Transcriber:
    """Factory. Defaults to the stub unless EVA_MEET_TRANSCRIBER=whisper."""
    choice = (name or os.environ.get("EVA_MEET_TRANSCRIBER", "stub")).lower()
    if choice in ("whisper", "whisper-cpp", "real"):
        return WhisperTranscriber()
    return StubTranscriber()
