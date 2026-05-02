from __future__ import annotations

import pytest

from services.audio import (
    FakeRecorder,
    Recorder,
    RECORDER_PROVIDERS,
    SoundDeviceRecorder,
    SoundDeviceUnavailableError,
    StoppableRecorder,
    build_recorder,
)
from services.audio.base import AudioClip


def test_fake_recorder_returns_silence_for_requested_duration() -> None:
    rec = FakeRecorder(sample_rate=16000)
    clip = rec.record(2.0)
    assert isinstance(clip, AudioClip)
    assert clip.sample_rate == 16000
    assert clip.channels == 1
    # 2 seconds * 16000 samples * 2 bytes = 64000 bytes of silence
    assert len(clip.samples) == 64000
    assert clip.samples == b"\x00" * 64000
    assert pytest.approx(clip.duration_seconds, rel=1e-6) == 2.0
    assert rec.last_duration == 2.0


def test_fake_recorder_returns_preset_samples_when_provided() -> None:
    canned = b"\x01\x02" * 10
    rec = FakeRecorder(samples=canned)
    clip = rec.record(0.1)
    assert clip.samples == canned


def test_audio_clip_duration_handles_zero_sample_rate() -> None:
    clip = AudioClip(samples=b"\x00\x00", sample_rate=0)
    assert clip.duration_seconds == 0.0


def test_build_recorder_dispatches_by_name() -> None:
    fake = build_recorder("fake", sample_rate=8000)
    assert isinstance(fake, FakeRecorder)
    assert fake.sample_rate == 8000

    sd = build_recorder("sounddevice", sample_rate=22050)
    assert isinstance(sd, SoundDeviceRecorder)
    assert sd.sample_rate == 22050


def test_build_recorder_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown recorder provider"):
        build_recorder("rtaudio")


def test_recorder_providers_constant_is_stable() -> None:
    assert "sounddevice" in RECORDER_PROVIDERS
    assert "fake" in RECORDER_PROVIDERS


def test_fake_recorder_satisfies_recorder_protocol() -> None:
    assert isinstance(FakeRecorder(), Recorder)


def test_sounddevice_recorder_raises_when_extras_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If sounddevice/numpy aren't installed, the recorder must fail loud."""
    rec = SoundDeviceRecorder()

    def fake_load(self):  # noqa: ARG001
        raise SoundDeviceUnavailableError("sounddevice/numpy are not installed.")

    monkeypatch.setattr(SoundDeviceRecorder, "_load_backend", fake_load)
    with pytest.raises(SoundDeviceUnavailableError, match="not installed"):
        rec.record(0.5)


def test_sounddevice_recorder_rejects_zero_duration() -> None:
    rec = SoundDeviceRecorder()
    with pytest.raises(Exception):
        rec.record(0)


def test_fake_recorder_satisfies_stoppable_protocol() -> None:
    assert isinstance(FakeRecorder(), StoppableRecorder)


def test_sounddevice_recorder_satisfies_stoppable_protocol() -> None:
    assert isinstance(SoundDeviceRecorder(), StoppableRecorder)
