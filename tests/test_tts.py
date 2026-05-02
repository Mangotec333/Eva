from __future__ import annotations

import subprocess

import pytest

from services.tts import (
    ConsoleSpeaker,
    MacOSSaySpeaker,
    MacOSSaySpeakerError,
    NullSpeaker,
    build_speaker,
)


def test_build_speaker_defaults_to_console() -> None:
    speaker = build_speaker("console")
    assert isinstance(speaker, ConsoleSpeaker)


def test_build_speaker_returns_macos_say() -> None:
    speaker = build_speaker("macos-say", voice="Samantha")
    assert isinstance(speaker, MacOSSaySpeaker)
    assert speaker.voice == "Samantha"


def test_build_speaker_no_speak_overrides_provider() -> None:
    speaker = build_speaker("macos-say", voice="Samantha", no_speak=True)
    assert isinstance(speaker, NullSpeaker)


def test_build_speaker_none_returns_null() -> None:
    assert isinstance(build_speaker("none"), NullSpeaker)


def test_build_speaker_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown TTS provider"):
        build_speaker("piper")


def test_console_speaker_prints(capsys: pytest.CaptureFixture[str]) -> None:
    ConsoleSpeaker().speak("hello")
    out = capsys.readouterr().out
    assert "EVA: hello" in out


def test_null_speaker_is_silent(capsys: pytest.CaptureFixture[str]) -> None:
    NullSpeaker().speak("hello")
    assert capsys.readouterr().out == ""


def test_macos_say_build_command_basic() -> None:
    speaker = MacOSSaySpeaker(say_path="/usr/bin/say", platform="darwin")
    cmd = speaker.build_command("hello world")
    assert cmd == ["/usr/bin/say", "--", "hello world"]


def test_macos_say_build_command_with_voice_and_rate() -> None:
    speaker = MacOSSaySpeaker(
        voice="Samantha",
        rate=180,
        say_path="/usr/bin/say",
        platform="darwin",
    )
    cmd = speaker.build_command("hi")
    assert cmd == ["/usr/bin/say", "-v", "Samantha", "-r", "180", "--", "hi"]


def test_macos_say_speak_invokes_subprocess_on_darwin() -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, check):
        calls.append(list(cmd))

        class Result:
            returncode = 0

        return Result()

    speaker = MacOSSaySpeaker(
        voice="Alex",
        say_path="/usr/bin/say",
        platform="darwin",
        runner=fake_run,
    )
    speaker.speak("good morning")
    assert calls == [["/usr/bin/say", "-v", "Alex", "--", "good morning"]]


def test_macos_say_raises_on_non_darwin() -> None:
    speaker = MacOSSaySpeaker(platform="linux")
    with pytest.raises(MacOSSaySpeakerError, match="only available on darwin"):
        speaker.speak("hi")


def test_macos_say_falls_back_when_explicitly_requested(
    capsys: pytest.CaptureFixture[str],
) -> None:
    speaker = MacOSSaySpeaker(platform="linux", fallback_to_print=True)
    speaker.speak("hello")
    assert "EVA: hello" in capsys.readouterr().out


def test_macos_say_propagates_called_process_error() -> None:
    def failing_run(cmd, check):  # noqa: ARG001
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    speaker = MacOSSaySpeaker(
        say_path="/usr/bin/say",
        platform="darwin",
        runner=failing_run,
    )
    with pytest.raises(MacOSSaySpeakerError, match="exited with status 1"):
        speaker.speak("boom")


def test_macos_say_filenotfound_without_fallback() -> None:
    def missing_runner(cmd, check):  # noqa: ARG001
        raise FileNotFoundError("not here")

    speaker = MacOSSaySpeaker(
        say_path="/usr/bin/say",
        platform="darwin",
        runner=missing_runner,
    )
    with pytest.raises(MacOSSaySpeakerError, match="executable not found"):
        speaker.speak("boom")


def test_macos_say_filenotfound_with_fallback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def missing_runner(cmd, check):  # noqa: ARG001
        raise FileNotFoundError("not here")

    speaker = MacOSSaySpeaker(
        say_path="/usr/bin/say",
        platform="darwin",
        runner=missing_runner,
        fallback_to_print=True,
    )
    speaker.speak("hello")
    assert "EVA: hello" in capsys.readouterr().out


def test_macos_say_resolves_path_via_shutil_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.tts.macos_say.shutil.which", lambda _: "/opt/bin/say")
    speaker = MacOSSaySpeaker(platform="darwin")
    assert speaker.build_command("x")[0] == "/opt/bin/say"


def test_macos_say_falls_back_to_default_path_if_which_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("services.tts.macos_say.shutil.which", lambda _: None)
    speaker = MacOSSaySpeaker(platform="darwin")
    assert speaker.build_command("x")[0] == "/usr/bin/say"
