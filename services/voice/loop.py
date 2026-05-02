from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from rich.console import Console

from services.audio.base import (
    AudioClip,
    Recorder,
    RecorderError,
    StopSignal,
    StoppableRecorder,
)
from services.audio.vad import SilenceConfig
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


def _capture_clip(
    *,
    recorder: Recorder,
    duration_seconds: float,
    silence_config: SilenceConfig | None,
    stop_signal: StopSignal | None,
    cli: Console,
) -> AudioClip:
    """Capture one turn's clip via the appropriate path.

    Without `silence_config`, falls back to the legacy fixed-window
    `record(duration)` for backward compatibility. With `silence_config`
    the recorder must implement `record_until_silence` (a `StoppableRecorder`).
    `stop_signal`, when supplied, lets a UI/bridge end the capture early.
    """
    if silence_config is None:
        cli.print(f"[dim]listening for {duration_seconds:.1f}s...[/dim]")
        return recorder.record(duration_seconds)

    if not isinstance(recorder, StoppableRecorder):
        raise RecorderError(
            f"recorder {type(recorder).__name__!r} does not support "
            "silence-completion; pass a StoppableRecorder or omit "
            "silence-timeout settings."
        )
    cli.print(
        f"[dim]listening (silence cutoff "
        f"{silence_config.silence_timeout_seconds:.1f}s, max "
        f"{silence_config.max_duration_seconds:.1f}s)...[/dim]"
    )
    return recorder.record_until_silence(
        silence_timeout_seconds=silence_config.silence_timeout_seconds,
        max_duration_seconds=silence_config.max_duration_seconds,
        threshold_rms=silence_config.threshold_rms,
        chunk_seconds=silence_config.chunk_seconds,
        stop_signal=stop_signal,
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
    silence_config: SilenceConfig | None = None,
    stop_signal: StopSignal | None = None,
) -> BrainResponse:
    """Run a single capture -> transcribe -> brain -> speak turn.

    Returns the BrainResponse so callers (CLI, tests) can assert on it.
    Audio capture and transcription errors propagate as `RecorderError` and
    `TranscriptionError`. The brain handles empty utterances itself by
    routing them through the clarification path.

    When `silence_config` is supplied the recorder must support
    `record_until_silence` — see `_capture_clip`. `stop_signal` is the
    chat-mic stop control; flipping it from another thread ends capture.
    """
    cli = console or Console()
    clip = _capture_clip(
        recorder=recorder,
        duration_seconds=duration_seconds,
        silence_config=silence_config,
        stop_signal=stop_signal,
        cli=cli,
    )
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
    silence_config: SilenceConfig | None = None,
    stop_signal: StopSignal | None = None,
) -> int:
    """Push-to-talk loop: prompt before each capture, exit on EOF/Ctrl-C.

    `prompt` returns a string before each turn. Tests inject a deterministic
    callable. The default uses `input(...)` and treats EOF as a graceful
    exit. `max_turns` bounds the loop in tests; production passes None.
    Returns the number of turns completed.

    `silence_config` switches the loop into hands-free silence-completion
    mode. `stop_signal` is a shared `StopSignal`; the loop clears it before
    each turn so a UI can reuse the same handle across turns.
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
    if silence_config is not None:
        cli.print(
            f"[dim]silence-completion: cutoff={silence_config.silence_timeout_seconds:.1f}s "
            f"max={silence_config.max_duration_seconds:.1f}s "
            f"threshold={silence_config.threshold_rms:.0f} rms[/dim]"
        )
        cli.print(
            "Press Enter to start; capture stops on silence, max-duration, "
            "or manual stop. Type 'q'+Enter to quit."
        )
    else:
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

        if stop_signal is not None:
            stop_signal.clear()

        try:
            await run_voice_turn(
                recorder=recorder,
                transcriber=transcriber,
                brain=brain,
                speaker=speaker,
                duration_seconds=duration_seconds,
                log_path=log_path,
                console=cli,
                silence_config=silence_config,
                stop_signal=stop_signal,
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
