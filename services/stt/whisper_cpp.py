from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Callable, Sequence

from services.audio.base import AudioClip
from services.stt.base import TranscriptionError


class WhisperCppUnavailableError(TranscriptionError):
    """Raised when the whisper.cpp binary or model cannot be used."""


def _write_wav(clip: AudioClip, path: Path) -> None:
    """Write an AudioClip out as a 16-bit PCM WAV that whisper.cpp accepts."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(clip.channels)
        wav.setsampwidth(clip.sample_width)
        wav.setframerate(clip.sample_rate)
        wav.writeframes(clip.samples)


class WhisperCppTranscriber:
    """Transcriber that shells out to a user-provided whisper.cpp binary.

    EVA does not bundle whisper.cpp. The user installs/builds it locally
    (e.g. https://github.com/ggerganov/whisper.cpp) and points EVA at the
    binary and a `.bin` model file. Audio never leaves the machine: the
    clip is written to a temp WAV, transcribed, then the temp file is
    deleted.

    The shell invocation is verified at construction time so a missing
    binary or model surfaces immediately rather than mid-conversation.
    """

    name = "whisper-cpp"

    def __init__(
        self,
        binary: str,
        model: str,
        *,
        language: str | None = None,
        threads: int | None = None,
        extra_args: Sequence[str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
        verify: bool = True,
    ) -> None:
        self.binary = binary
        self.model = model
        self.language = language
        self.threads = threads
        self.extra_args = list(extra_args) if extra_args else []
        self._runner = runner or subprocess.run
        if verify:
            self._verify()

    def _verify(self) -> None:
        if not os.path.exists(self.binary):
            raise WhisperCppUnavailableError(
                f"whisper.cpp binary not found at {self.binary}. "
                "Build whisper.cpp and pass --whisper-bin to point at the `main` binary."
            )
        if not os.path.exists(self.model):
            raise WhisperCppUnavailableError(
                f"whisper.cpp model not found at {self.model}. "
                "Download a ggml model and pass --whisper-model."
            )

    def build_command(self, wav_path: str) -> list[str]:
        cmd: list[str] = [
            self.binary,
            "-m",
            self.model,
            "-f",
            wav_path,
            "-otxt",
            "-nt",  # no timestamps in stdout
        ]
        if self.language:
            cmd += ["-l", self.language]
        if self.threads is not None:
            cmd += ["-t", str(self.threads)]
        cmd += list(self.extra_args)
        return cmd

    def transcribe(self, clip: AudioClip) -> str:
        with tempfile.TemporaryDirectory(prefix="eva-stt-") as tmpdir:
            wav_path = Path(tmpdir) / "input.wav"
            _write_wav(clip, wav_path)
            cmd = self.build_command(str(wav_path))
            try:
                result = self._runner(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except FileNotFoundError as exc:
                raise WhisperCppUnavailableError(
                    f"whisper.cpp binary could not be executed: {exc}"
                ) from exc
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                raise TranscriptionError(
                    f"whisper.cpp exited with status {exc.returncode}: {stderr}"
                ) from exc

        text = (result.stdout or "").strip()
        if not text:
            return ""
        return _clean_whisper_output(text)


def _clean_whisper_output(text: str) -> str:
    """Strip the bracketed metadata lines whisper.cpp prints alongside text."""
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        cleaned_lines.append(line)
    return " ".join(cleaned_lines).strip()


__all__ = ["WhisperCppTranscriber", "WhisperCppUnavailableError", "_write_wav"]


def _round_trip_self_test() -> None:  # pragma: no cover - dev helper
    """Sanity-check WAV writer roundtrip; not exercised in test suite."""
    clip = AudioClip(
        samples=struct.pack("<h", 0) * 8000,
        sample_rate=16000,
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.wav"
        _write_wav(clip, p)
        assert p.exists()
