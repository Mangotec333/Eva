from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from rich.console import Console

from services.model.provider import HeuristicModelProvider
from services.reminders.scheduler import ReminderJob
from services.tts import NullSpeaker
from services.voice import cli as voice_cli


class _RecordingSpeaker:
    name = "recording"

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def test_build_reminder_sink_speaks_reminder() -> None:
    speaker = _RecordingSpeaker()
    sink = voice_cli.build_reminder_sink(speaker, cli=Console(quiet=True))
    sink(ReminderJob(fire_at=0.0, seq=0, message="stand up", job_id="x"))
    assert speaker.spoken == ["Reminder: stand up"]


@pytest.mark.asyncio
async def test_run_text_loop_schedules_and_fires_reminder(tmp_path, monkeypatch) -> None:
    """End-to-end CLI: typed reminder gets scheduled and fires via the live runner."""
    speaker = _RecordingSpeaker()
    log_path = tmp_path / "tasks.jsonl"

    inputs = iter(["remind me in 1 second to test the microphone", EOFError()])

    def fake_input(_prompt: str) -> str:
        item = next(inputs)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(voice_cli, "_blocking_input", fake_input)

    await asyncio.wait_for(
        voice_cli.run_text_loop(
            log_path=Path(log_path),
            model_provider=HeuristicModelProvider(),
            speaker=speaker,
        ),
        timeout=5.0,
    )

    # The confirmation is spoken first; the fired reminder is spoken when due.
    confirmations = [s for s in speaker.spoken if s.startswith("Okay,")]
    fires = [s for s in speaker.spoken if s.startswith("Reminder:")]
    assert any("test the microphone" in c for c in confirmations)
    assert any("test the microphone" in f for f in fires)


def test_run_text_loop_handles_invalid_reminder_without_scheduling(
    tmp_path, monkeypatch
) -> None:
    speaker = _RecordingSpeaker()
    log_path = tmp_path / "tasks.jsonl"

    inputs = iter(["remind me in 2 days to water plants", EOFError()])

    def fake_input(_prompt: str) -> str:
        item = next(inputs)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(voice_cli, "_blocking_input", fake_input)

    asyncio.run(
        voice_cli.run_text_loop(
            log_path=Path(log_path),
            model_provider=HeuristicModelProvider(),
            speaker=speaker,
        )
    )

    clarifications = [s for s in speaker.spoken if "Unsupported time unit" in s]
    fires = [s for s in speaker.spoken if s.startswith("Reminder:")]
    assert clarifications, speaker.spoken
    assert fires == []


def test_no_speak_sink_is_quiet() -> None:
    sink = voice_cli.build_reminder_sink(NullSpeaker(), cli=Console(quiet=True))
    # Should not raise; NullSpeaker absorbs the message.
    sink(ReminderJob(fire_at=0.0, seq=0, message="x", job_id="x"))
