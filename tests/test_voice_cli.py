from __future__ import annotations

import pytest

from services.audio import FakeRecorder, SoundDeviceRecorder
from services.audio.base import AudioClip
from services.stt import TextTranscriber, build_transcriber
from services.voice.cli import (
    DEFAULT_RECORDER,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_STT_PROVIDER,
    DEFAULT_VOICE_DURATION,
    build_arg_parser,
)


def test_cli_parses_voice_defaults() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["voice"])
    assert args.command == "voice"
    assert args.duration == DEFAULT_VOICE_DURATION
    assert args.recorder == DEFAULT_RECORDER
    assert args.recorder == "sounddevice"
    assert args.stt_provider == DEFAULT_STT_PROVIDER
    assert args.stt_provider == "text"
    assert args.sample_rate == DEFAULT_SAMPLE_RATE
    assert args.tts_provider == "console"
    assert args.model_provider == "heuristic"
    assert args.whisper_bin is None
    assert args.whisper_model is None
    assert args.mock_utterance is None


def test_cli_parses_voice_full_options() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "voice",
            "--duration",
            "3.5",
            "--recorder",
            "fake",
            "--sample-rate",
            "22050",
            "--stt-provider",
            "whisper-cpp",
            "--whisper-bin",
            "/opt/whisper/main",
            "--whisper-model",
            "/opt/whisper/ggml-base.bin",
            "--mock-utterance",
            "ignored when whisper",
            "--model-provider",
            "ollama",
            "--ollama-base-url",
            "http://127.0.0.1:11434",
            "--ollama-model",
            "llama3.2",
            "--tts-provider",
            "macos-say",
            "--voice",
            "Samantha",
        ]
    )
    assert args.duration == 3.5
    assert args.recorder == "fake"
    assert args.sample_rate == 22050
    assert args.stt_provider == "whisper-cpp"
    assert args.whisper_bin == "/opt/whisper/main"
    assert args.whisper_model == "/opt/whisper/ggml-base.bin"
    assert args.model_provider == "ollama"
    assert args.tts_provider == "macos-say"
    assert args.voice == "Samantha"


def test_cli_voice_rejects_unknown_recorder() -> None:
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["voice", "--recorder", "alsa"])


def test_cli_voice_rejects_unknown_stt() -> None:
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["voice", "--stt-provider", "deepgram"])


def test_cli_voice_no_speak_flag() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["voice", "--no-speak"])
    assert args.no_speak is True


def test_cli_voice_to_recorder_wiring_fake() -> None:
    from services.audio import build_recorder

    parser = build_arg_parser()
    args = parser.parse_args(["voice", "--recorder", "fake", "--sample-rate", "8000"])
    recorder = build_recorder(args.recorder, sample_rate=args.sample_rate)
    assert isinstance(recorder, FakeRecorder)
    assert recorder.sample_rate == 8000


def test_cli_voice_to_recorder_wiring_sounddevice_constructs() -> None:
    """Constructing the sounddevice recorder must not import sounddevice."""
    from services.audio import build_recorder

    recorder = build_recorder("sounddevice", sample_rate=16000)
    assert isinstance(recorder, SoundDeviceRecorder)


def test_cli_voice_to_text_transcriber_wiring() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        ["voice", "--stt-provider", "text", "--mock-utterance", "what's the weather"]
    )
    t = build_transcriber(
        args.stt_provider,
        whisper_bin=args.whisper_bin,
        whisper_model=args.whisper_model,
        fixed_text=args.mock_utterance,
    )
    assert isinstance(t, TextTranscriber)
    clip = AudioClip(samples=b"\x00\x00", sample_rate=16000)
    assert t.transcribe(clip) == "what's the weather"


def test_cli_voice_whisper_wiring_requires_paths() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["voice", "--stt-provider", "whisper-cpp"])
    with pytest.raises(ValueError, match="requires --whisper-bin"):
        build_transcriber(
            args.stt_provider,
            whisper_bin=args.whisper_bin,
            whisper_model=args.whisper_model,
        )


def test_cli_voice_log_path_default() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["voice"])
    assert args.log_path == "data/voice_tasks.jsonl"
