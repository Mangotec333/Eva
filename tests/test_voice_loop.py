from __future__ import annotations

import asyncio
import json
from pathlib import Path

from services.audio import FakeRecorder
from services.audio.base import AudioClip, RecorderError
from services.brain.orchestrator import BrainOrchestrator
from services.model.provider import ModelProvider
from services.stt import TextTranscriber, TranscriptionError
from services.tts import NullSpeaker
from services.voice.loop import (
    append_voice_log,
    run_voice_loop,
    run_voice_turn,
)


class StaticModelProvider(ModelProvider):
    def __init__(self, answer: str = "stub answer") -> None:
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


def _run(coro):
    return asyncio.run(coro)


def test_run_voice_turn_pipes_capture_through_brain() -> None:
    recorder = FakeRecorder(sample_rate=16000)
    transcriber = TextTranscriber(fixed_text="what time is it")
    model = StaticModelProvider("It is noon.")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(model)

    response = _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.5,
        )
    )

    assert recorder.last_duration == 1.5
    assert model.calls == ["what time is it"]
    assert response.text == "It is noon."
    assert speaker.spoken == ["It is noon."]


def test_run_voice_turn_routes_approval_path_through_brain() -> None:
    recorder = FakeRecorder()
    transcriber = TextTranscriber(fixed_text="delete every file in tmp")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("ignored"))

    response = _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.0,
        )
    )

    assert response.status.value == "needs_approval"
    assert speaker.spoken[0].startswith("I can help with that")


def test_run_voice_turn_handles_empty_transcript_via_clarification() -> None:
    recorder = FakeRecorder()
    transcriber = TextTranscriber(fixed_text="")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    response = _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.0,
        )
    )

    assert response.status.value == "needs_clarification"
    assert "did not catch" in speaker.spoken[0].lower()


def test_run_voice_turn_writes_log(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "voice.jsonl"
    recorder = FakeRecorder()
    transcriber = TextTranscriber(fixed_text="hello eva")
    speaker = NullSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("hi back"))

    _run(
        run_voice_turn(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.0,
            log_path=log,
        )
    )

    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["utterance"] == "hello eva"
    assert payload["response"] == "hi back"
    assert payload["source"] == "voice"
    assert payload["status"] == "completed"


def test_append_voice_log_creates_parent_dirs(tmp_path: Path) -> None:
    from services.brain.schema import BrainResponse, TaskRequest, TaskStatus

    log = tmp_path / "deep" / "nested" / "voice.jsonl"
    request = TaskRequest(source="voice", utterance="hi")
    response = BrainResponse(
        task_id=request.task_id,
        status=TaskStatus.COMPLETED,
        spoken_summary="hi",
        text="hi",
    )
    append_voice_log(log, request, response)
    assert log.exists()


class ExplodingRecorder:
    name = "exploding"
    sample_rate = 16000
    channels = 1

    def record(self, duration_seconds: float) -> AudioClip:  # noqa: ARG002
        raise RecorderError("mic unplugged")


def test_run_voice_loop_recovers_from_recorder_error() -> None:
    recorder = ExplodingRecorder()
    transcriber = TextTranscriber()
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.0,
            prompt=lambda: "",
            max_turns=2,
        )
    )

    assert turns == 2
    assert speaker.spoken == []  # no successful turn produced speech


class ExplodingTranscriber:
    name = "exploding"

    def transcribe(self, clip: AudioClip) -> str:  # noqa: ARG002
        raise TranscriptionError("whisper crashed")


def test_run_voice_loop_recovers_from_transcription_error() -> None:
    recorder = FakeRecorder()
    transcriber = ExplodingTranscriber()
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=1.0,
            prompt=lambda: "",
            max_turns=1,
        )
    )

    assert turns == 1
    assert speaker.spoken == []


def test_run_voice_loop_quits_on_q_command() -> None:
    recorder = FakeRecorder()
    transcriber = TextTranscriber(fixed_text="hi")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider("hello back"))

    inputs = iter(["", "q"])

    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=0.5,
            prompt=lambda: next(inputs),
            max_turns=10,
        )
    )

    assert turns == 1
    # one turn spoke "hello back", then quit said "Standing by."
    assert speaker.spoken == ["hello back", "Standing by."]


def test_run_voice_loop_exits_on_eof() -> None:
    recorder = FakeRecorder()
    transcriber = TextTranscriber()
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    def prompt_eof() -> str:
        raise EOFError

    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=0.5,
            prompt=prompt_eof,
            max_turns=10,
        )
    )

    assert turns == 0
    assert speaker.spoken == ["Standing by."]


def test_run_voice_loop_runs_multiple_turns(tmp_path: Path) -> None:
    recorder = FakeRecorder()
    transcriber = TextTranscriber(utterances=["one", "two", "three"], fixed_text="x")
    speaker = CapturingSpeaker()
    model = StaticModelProvider("ok")
    brain = BrainOrchestrator(model)

    inputs = iter(["", "", ""])

    turns = _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=0.5,
            prompt=lambda: next(inputs),
            max_turns=3,
            log_path=tmp_path / "voice.jsonl",
        )
    )

    assert turns == 3
    assert model.calls == ["one", "two", "three"]
    assert speaker.spoken == ["ok", "ok", "ok"]
    log_lines = (tmp_path / "voice.jsonl").read_text().strip().splitlines()
    assert len(log_lines) == 3


def test_run_voice_loop_prints_clarify_on_empty(tmp_path: Path) -> None:
    """Empty utterances are handled by the brain (clarify), not dropped."""
    recorder = FakeRecorder()
    transcriber = TextTranscriber(fixed_text="")
    speaker = CapturingSpeaker()
    brain = BrainOrchestrator(StaticModelProvider())

    _run(
        run_voice_loop(
            recorder=recorder,
            transcriber=transcriber,
            brain=brain,
            speaker=speaker,
            duration_seconds=0.5,
            prompt=lambda: "",
            max_turns=1,
        )
    )

    assert any("did not catch" in s.lower() for s in speaker.spoken)
