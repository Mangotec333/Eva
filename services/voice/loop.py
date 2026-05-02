from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from rich.console import Console

from services.audio.base import Recorder, RecorderError
from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import BrainResponse, TaskRequest
from services.stt.base import Transcriber, TranscriptionError
from services.tts import Speaker


def append_voice_log(
    path: Path,
    request: TaskRequest,
    response: BrainResponse,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "task_id": request.task_id,
                    "source": request.source,
                    "utterance": request.utterance,
                    "response": response.text,
                    "status": response.status.value,
                    "timestamp": request.timestamp.isoformat(),
                }
            )
            + "\n"
        )


async def run_voice_turn(
    *,
    recorder: Recorder,
    transcriber: Transcriber,
    brain: BrainOrchestrator,
    speaker: Speaker,
    duration_seconds: float,
    log_path: Path | None = None,
    console: Console | None = None,
) -> BrainResponse:
    """Run a single capture -> transcribe -> brain -> speak turn.

    Returns the BrainResponse so callers (CLI, tests) can assert on it.
    Audio capture and transcription errors propagate as `RecorderError` and
    `TranscriptionError`. The brain handles empty utterances itself by
    routing them through the clarification path.
    """
    cli = console or Console()
    cli.print(f"[dim]listening for {duration_seconds:.1f}s...[/dim]")
    clip = recorder.record(duration_seconds)
    cli.print(
        f"[dim]captured {clip.duration_seconds:.1f}s @ "
        f"{clip.sample_rate}Hz[/dim]"
    )

    utterance = transcriber.transcribe(clip)
    cli.print(f"You: {utterance}")

    request = TaskRequest(source="voice", utterance=utterance)
    response = await brain.handle(request)
    speaker.speak(response.spoken_summary)

    if log_path is not None:
        append_voice_log(log_path, request, response)
    return response


async def run_voice_loop(
    *,
    recorder: Recorder,
    transcriber: Transcriber,
    brain: BrainOrchestrator,
    speaker: Speaker,
    duration_seconds: float,
    log_path: Path | None = None,
    console: Console | None = None,
    prompt: Callable[[], str] | None = None,
    max_turns: int | None = None,
) -> int:
    """Push-to-talk loop: prompt before each capture, exit on EOF/Ctrl-C.

    `prompt` returns a string before each turn. Tests inject a deterministic
    callable. The default uses `input(...)` and treats EOF as a graceful
    exit. `max_turns` bounds the loop in tests; production passes None.
    Returns the number of turns completed.
    """
    cli = console or Console()
    prompter = prompt or _interactive_prompt
    turns = 0

    cli.print("[bold]EVA voice loop[/bold]")
    cli.print(
        f"Recorder: [cyan]{getattr(recorder, 'name', type(recorder).__name__)}[/cyan]  "
        f"STT: [cyan]{getattr(transcriber, 'name', type(transcriber).__name__)}[/cyan]  "
        f"TTS: [cyan]{getattr(speaker, 'name', type(speaker).__name__)}[/cyan]"
    )
    cli.print(
        f"Press Enter to record {duration_seconds:.1f}s, "
        "type 'q'+Enter to quit, or Ctrl-D/Ctrl-C to exit."
    )

    while True:
        if max_turns is not None and turns >= max_turns:
            return turns
        try:
            command = prompter()
        except (EOFError, KeyboardInterrupt):
            cli.print()
            speaker.speak("Standing by.")
            return turns

        if command.strip().lower() in {"q", "quit", "exit"}:
            speaker.speak("Standing by.")
            return turns

        try:
            await run_voice_turn(
                recorder=recorder,
                transcriber=transcriber,
                brain=brain,
                speaker=speaker,
                duration_seconds=duration_seconds,
                log_path=log_path,
                console=cli,
            )
        except RecorderError as exc:
            cli.print(f"[red]Recorder error:[/red] {exc}")
        except TranscriptionError as exc:
            cli.print(f"[red]Transcription error:[/red] {exc}")
        turns += 1


def _interactive_prompt() -> str:
    return input("[press Enter to record] ")


def run_voice_loop_sync(**kwargs) -> int:
    return asyncio.run(run_voice_loop(**kwargs))
