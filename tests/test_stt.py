from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

from services.audio.base import AudioClip
from services.stt import (
    STT_PROVIDERS,
    TextTranscriber,
    Transcriber,
    TranscriptionError,
    WhisperCppTranscriber,
    WhisperCppUnavailableError,
    build_transcriber,
)
from services.stt.whisper_cpp import _clean_whisper_output, _write_wav


def _make_clip() -> AudioClip:
    return AudioClip(samples=b"\x00\x00" * 1600, sample_rate=16000)


def test_text_transcriber_returns_fixed_text() -> None:
    t = TextTranscriber("ping")
    assert t.transcribe(_make_clip()) == "ping"


def test_text_transcriber_drains_queue_then_falls_back() -> None:
    t = TextTranscriber("fallback", utterances=["one", "two"])
    assert t.transcribe(_make_clip()) == "one"
    assert t.transcribe(_make_clip()) == "two"
    assert t.transcribe(_make_clip()) == "fallback"


def test_text_transcriber_records_calls() -> None:
    t = TextTranscriber()
    t.transcribe(_make_clip())
    t.transcribe(_make_clip())
    assert len(t.transcribe_calls) == 2


def test_text_transcriber_satisfies_protocol() -> None:
    assert isinstance(TextTranscriber(), Transcriber)


def test_build_transcriber_text_default() -> None:
    t = build_transcriber("text")
    assert isinstance(t, TextTranscriber)
    assert t.fixed_text == "hello eva"


def test_build_transcriber_text_with_fixed() -> None:
    t = build_transcriber("text", fixed_text="hi there")
    assert t.fixed_text == "hi there"


def test_build_transcriber_whisper_requires_paths() -> None:
    with pytest.raises(ValueError, match="requires --whisper-bin"):
        build_transcriber("whisper-cpp")


def test_build_transcriber_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown STT provider"):
        build_transcriber("vosk")


def test_stt_providers_constant() -> None:
    assert "text" in STT_PROVIDERS
    assert "whisper-cpp" in STT_PROVIDERS


def test_clean_whisper_output_strips_brackets() -> None:
    raw = "[BLANK_AUDIO]\nhello world\n[00:00.000 --> 00:01.000]\n"
    assert _clean_whisper_output(raw) == "hello world"


def test_clean_whisper_output_joins_lines() -> None:
    raw = "hello\nworld\n"
    assert _clean_whisper_output(raw) == "hello world"


def test_write_wav_roundtrips(tmp_path: Path) -> None:
    clip = AudioClip(samples=b"\x10\x20" * 800, sample_rate=16000)
    path = tmp_path / "out.wav"
    _write_wav(clip, path)
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.readframes(wav.getnframes()) == clip.samples


def test_whisper_cpp_verifies_binary_exists(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"")
    with pytest.raises(WhisperCppUnavailableError, match="binary not found"):
        WhisperCppTranscriber(binary=str(tmp_path / "missing"), model=str(model))


def test_whisper_cpp_verifies_model_exists(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    binary.write_bytes(b"")
    with pytest.raises(WhisperCppUnavailableError, match="model not found"):
        WhisperCppTranscriber(binary=str(binary), model=str(tmp_path / "absent.bin"))


def test_whisper_cpp_build_command_includes_options(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"")
    model.write_bytes(b"")
    t = WhisperCppTranscriber(
        binary=str(binary),
        model=str(model),
        language="en",
        threads=4,
        extra_args=["--no-prints"],
    )
    cmd = t.build_command("/tmp/x.wav")
    assert cmd[0] == str(binary)
    assert "-m" in cmd and str(model) in cmd
    assert "-f" in cmd and "/tmp/x.wav" in cmd
    assert "-l" in cmd and "en" in cmd
    assert "-t" in cmd and "4" in cmd
    assert "--no-prints" in cmd


def test_whisper_cpp_transcribe_runs_binary_and_cleans_output(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"")
    model.write_bytes(b"")

    captured: dict[str, list[str]] = {}

    def fake_runner(cmd, capture_output, text, check):  # noqa: ARG001
        captured["cmd"] = list(cmd)

        class Result:
            returncode = 0
            stdout = "[BLANK_AUDIO]\n hello eva \n"
            stderr = ""

        return Result()

    t = WhisperCppTranscriber(
        binary=str(binary),
        model=str(model),
        runner=fake_runner,
    )
    clip = _make_clip()
    text = t.transcribe(clip)
    assert text == "hello eva"
    assert captured["cmd"][0] == str(binary)
    # The wav is written to a temp dir, so just check the flag is present
    assert "-f" in captured["cmd"]


def test_whisper_cpp_transcribe_propagates_called_process_error(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"")
    model.write_bytes(b"")

    def boom(cmd, capture_output, text, check):  # noqa: ARG001
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd, stderr="bad model")

    t = WhisperCppTranscriber(binary=str(binary), model=str(model), runner=boom)
    with pytest.raises(TranscriptionError, match="exited with status 2"):
        t.transcribe(_make_clip())


def test_whisper_cpp_transcribe_handles_missing_binary_at_runtime(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"")
    model.write_bytes(b"")

    def missing(cmd, capture_output, text, check):  # noqa: ARG001
        raise FileNotFoundError("gone")

    t = WhisperCppTranscriber(binary=str(binary), model=str(model), runner=missing)
    with pytest.raises(WhisperCppUnavailableError, match="could not be executed"):
        t.transcribe(_make_clip())


def test_whisper_cpp_transcribe_returns_empty_string_for_blank_output(tmp_path: Path) -> None:
    binary = tmp_path / "main"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"")
    model.write_bytes(b"")

    def empty(cmd, capture_output, text, check):  # noqa: ARG001
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    t = WhisperCppTranscriber(binary=str(binary), model=str(model), runner=empty)
    assert t.transcribe(_make_clip()) == ""
