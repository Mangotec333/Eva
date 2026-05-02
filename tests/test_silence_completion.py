from __future__ import annotations

import asyncio
import threading

import pytest

from services.audio import FakeRecorder, StopSignal
from services.audio.base import AudioClip, RecorderError
from services.audio.vad import SilenceConfig, chunk_rms, is_silent
from services.brain.orchestrator import BrainOrchestrator
from services.model.provider import ModelProvider
from services.stt import TextTranscriber
from services.tts import NullSpeaker
from services.voice.loop import run_voice_loop, run_voice_turn


class StaticModelProvider(ModelProvider):
    def __init__(self, answer: str = "ok") -> None:
        self._answer = answer
        self.calls: list[str] = []

    async def answer(self, utterance: str) -> str:
        self.calls.append(utterance)
        return self._answer


class CapturingSpeaker:
    name = "capturing"

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def _silent_chunk(sample_rate: int = 16000, chunk_seconds: float = 0.1) -> bytes:
    frames = int(sample_rate * chunk_seconds)
    return b"\x00\x00" * frames


def _loud_chunk(sample_rate: int = 16000, chunk_seconds: float = 0.1, value: int = 5000) -> bytes:
    frames = int(sample_rate * chunk_seconds)
    sample = value.to_bytes(2, "little", signed=True)
    return sample * frames


# --- VAD primitives ---------------------------------------------------------


def test_chunk_rms_returns_zero_for_silence() -> None:
    assert chunk_rms(_silent_chunk()) == 0.0


def test_chunk_rms_detects_loud_chunk() -> None:
    rms = chunk_rms(_loud_chunk(value=8000))
    assert rms == pytest.approx(8000.0, rel=1e-3)


def test_chunk_rms_handles_empty_buffer() -> None:
    assert chunk_rms(b"") == 0.0


def test_chunk_rms_truncates_odd_byte() -> None:
    # Trailing odd byte from a short read must not crash.
    assert chunk_rms(b"\x00\x00\x05") == 0.0


def test_chunk_rms_rejects_non_pcm16() -> None:
    with pytest.raises(ValueError):
        chunk_rms(b"\x00\x00\x00\x00", sample_width=4)


def test_is_silent_threshold() -> None:
    assert is_silent(_silent_chunk(), threshold_rms=100.0)
    assert not is_silent(_loud_chunk(value=5000), threshold_rms=100.0)


# --- FakeRecorder.record_until_silence --------------------------------------


def test_fake_recorder_stops_on_trailing_silence() -> None:
    chunks = (
        [_loud_chunk()] * 5  # 0.5s of speech
        + [_silent_chunk()] * 6  # 0.6s of silence (> 0.5s cutoff)
        + [_loud_chunk()] * 100  # never reached
    )
    rec = FakeRecorder(chunks=chunks)
    clip = rec.record_until_silence(
        silence_timeout_seconds=0.5,
        max_duration_seconds=10.0,
        threshold_rms=300.0,
        chunk_seconds=0.1,
    )
    assert isinstance(clip, AudioClip)
    assert rec.last_stop_reason == "silence_timeout"
    # 5 loud + 5 silent (0.5s = silence_timeout) + the chunk that pushed it over
    # = 11 chunks, but the loop breaks the chunk that takes trailing >= cutoff.
    assert clip.duration_seconds == pytest.approx(1.0, rel=1e-3)


def test_fake_recorder_caps_at_max_duration() -> None:
    chunks = [_loud_chunk()] * 1000
    rec = FakeRecorder(chunks=chunks)
    clip = rec.record_until_silence(
        silence_timeout_seconds=1.0,
        max_duration_seconds=0.5,
        threshold_rms=300.0,
        chunk_seconds=0.1,
    )
    assert rec.last_stop_reason == "max_duration"
    assert clip.duration_seconds == pytest.approx(0.5, rel=1e-2)


def test_fake_recorder_manual_stop_signal_ends_capture_immediately() -> None:
    chunks = [_loud_chunk()] * 1000
    rec = FakeRecorder(chunks=chunks)
    stop = StopSignal()
    stop.stop()  # already raised — first iteration should bail out
    clip = rec.record_until_silence(
        silence_timeout_seconds=10.0,
        max_duration_seconds=10.0,
        threshold_rms=300.0,
        chunk_seconds=0.1,
        stop_signal=stop,
    )
    assert rec.last_stop_reason == "manual_stop"
    assert clip.samples == b""


def test_fake_recorder_manual_stop_after_some_speech() -> None:
    """Stop signal flipped mid-stream ends capture on the next chunk."""
    stop = StopSignal()

    def stepping_chunks():
        for i in range(10):
            if i == 2:
                stop.stop()
            yield _loud_chunk()

    rec_step = FakeRecorder(chunks=stepping_chunks())
    clip = rec_step.record_until_silence(
        silence_timeout_seconds=10.0,
        max_duration_seconds=10.0,
        threshold_rms=300.0,
        stop_signal=stop,
    )
    assert rec_step.last_stop_reason == "manual_stop"
    # Two chunks extended before the loop sees the signal on iter 2's
    # post-yield check; the third chunk that fired the stop is dropped.
    assert clip.duration_seconds == pytest.approx(0.2, rel=1e-2)


def test_fake_recorder_default_silence_iter_stops_on_timeout() -> None:
    """Without scripted chunks, the FakeRecorder produces silence and the
    silence-timeout path must terminate."""
    rec = FakeRecorder()
    clip = rec.record_until_silence(
        silence_timeout_seconds=0.3,
        max_duration_seconds=10.0,
        threshold_rms=100.0,
        chunk_seconds=0.1,
    )
    assert rec.last_stop_reason == "silence_timeout"
    assert clip.duration_seconds == pytest.approx(0.3, rel=1e-2)


# --- StopSignal -------------------------------------------------------------


def test_stop_signal_is_thread_safe() -> None:
    sig = StopSignal()
    assert not sig.is_set()

    def fire():
        sig.stop()

    t = threading.Thread(target=fire)
    t.start()
    t.join()
    assert sig.is_set()
    sig.clear()
    assert not sig.is_set()


# --- voice loop integration -------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_run_voice_turn_uses_silence_config_when_supplied() -> None:
    chunks = [_loud_chunk()] * 3 + [_silent_chunk()] * 5
    recorder = FakeRecorder(chunks=chunks)
    transcriber = TextTranscriber(fixed_text="hands free")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("got it"))

    cfg = SilenceConfig(
        threshold_rms=300.0,
        silence_timeout_seconds=0.4,
        max_duration_seconds=5.0,
        chunk_seconds=0.1,
    )

    response = _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=99.0,  # ignored when silence_config is set
            silence_config=cfg,
        )
    )
    assert recorder.last_stop_reason == "silence_timeout"
    assert response.text == "got it"
    assert speaker.spoken == ["got it"]


def test_run_voice_turn_rejects_silence_on_non_stoppable_recorder() -> None:
    class LegacyRecorder:
        name = "legacy"
        sample_rate = 16000
        channels = 1

        def record(self, duration_seconds: float) -> AudioClip:  # noqa: ARG002
            return AudioClip(samples=b"", sample_rate=16000)

    recorder = LegacyRecorder()
    transcriber = TextTranscriber()
    speaker = NullSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    cfg = SilenceConfig(silence_timeout_seconds=0.5, max_duration_seconds=5.0)

    with pytest.raises(RecorderError, match="does not support"):
        _run(
            run_voice_turn(
                recorder=recorder,
                transcriber=transcriber,
                brain=brain,
                speaker=speaker,
                duration_seconds=1.0,
                silence_config=cfg,
            )
        )


def test_run_voice_loop_clears_stop_signal_between_turns() -> None:
    """A pre-fired StopSignal should be cleared at the start of each turn so
    the chat-mic UX (one button per turn) doesn't latch."""
    chunks = [_loud_chunk()] * 2 + [_silent_chunk()] * 5
    recorder = FakeRecorder(chunks=chunks * 3)
    transcriber = TextTranscriber(fixed_text="hi")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("ack"))
    stop = StopSignal()
    stop.stop()  # pre-fired; should be cleared before first turn

    cfg = SilenceConfig(
        threshold_rms=300.0,
        silence_timeout_seconds=0.4,
        max_duration_seconds=2.0,
        chunk_seconds=0.1,
    )

    inputs = iter(["", "q"])
    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=99.0,
            prompt=lambda: next(inputs),
            max_turns=5,
            silence_config=cfg,
            stop_signal=stop,
        )
    )
    assert turns == 1
    assert speaker.spoken == ["ack", "Standing by."]
    # After the turn ran, the signal should be unset (cleared at turn start,
    # never re-set by anyone in this test).
    assert not stop.is_set()


def test_run_voice_loop_manual_stop_truncates_turn() -> None:
    """A UI thread firing StopSignal mid-turn ends recording promptly."""
    stop = StopSignal()

    def stepping_chunks():
        for i in range(1000):
            if i == 2:
                stop.stop()
            yield _loud_chunk()

    recorder = FakeRecorder(chunks=stepping_chunks())
    transcriber = TextTranscriber(fixed_text="cut me off")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("done"))

    cfg = SilenceConfig(
        threshold_rms=100.0,
        silence_timeout_seconds=10.0,
        max_duration_seconds=10.0,
        chunk_seconds=0.1,
    )

    inputs = iter(["", "q"])
    _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=99.0,
            prompt=lambda: next(inputs),
            max_turns=5,
            silence_config=cfg,
            stop_signal=stop,
        )
    )
    assert recorder.last_stop_reason == "manual_stop"


def test_run_voice_turn_legacy_duration_path_unchanged() -> None:
    """The pre-existing fixed-duration API must still work without
    silence_config, preserving backward compatibility."""
    recorder = FakeRecorder(sample_rate=16000)
    transcriber = TextTranscriber(fixed_text="legacy path")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("ok"))

    response = _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=2.0,
        )
    )
    assert recorder.last_duration == 2.0
    assert response.text == "ok"
