from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console

from services.audio import RECORDER_PROVIDERS, build_recorder
from services.audio.vad import SilenceConfig
from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import TaskRequest
from services.model.ollama import OllamaProvider
from services.model.provider import HeuristicModelProvider, ModelProvider
from services.reminders import ReminderJob, ReminderScheduler
from services.stt import STT_PROVIDERS, build_transcriber
from services.tts import TTS_PROVIDERS, Speaker, build_speaker
from services.voice.loop import run_voice_loop

console = Console()

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_TTS_PROVIDER = "console"
DEFAULT_STT_PROVIDER = "text"
DEFAULT_RECORDER = "sounddevice"
DEFAULT_VOICE_DURATION = 5.0
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SILENCE_TIMEOUT = 1.2
DEFAULT_SILENCE_THRESHOLD = 350.0
DEFAULT_MAX_DURATION = 30.0
DEFAULT_CHUNK_SECONDS = 0.1


def build_model_provider(
    provider: str,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
) -> ModelProvider:
    if provider == "heuristic":
        return HeuristicModelProvider()
    if provider == "ollama":
        return OllamaProvider(base_url=ollama_base_url, model=ollama_model)
    raise ValueError(f"Unknown model provider: {provider}")


def append_task_log(path: Path, request: TaskRequest, response_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "task_id": request.task_id,
                    "source": request.source,
                    "utterance": request.utterance,
                    "response": response_text,
                    "timestamp": request.timestamp.isoformat(),
                }
            )
            + "\n"
        )


def build_reminder_sink(speaker: Speaker, cli: Console = console):
    """Sink that announces a fired reminder via console + TTS."""

    def _sink(job: ReminderJob) -> None:
        text = f"Reminder: {job.message}"
        cli.print(f"[bold magenta]{text}[/bold magenta]")
        speaker.speak(text)

    return _sink


async def run_text_loop(
    log_path: Path,
    model_provider: ModelProvider,
    speaker: Speaker | None = None,
) -> None:
    speaker = speaker or build_speaker(DEFAULT_TTS_PROVIDER)
    scheduler = ReminderScheduler(sink=build_reminder_sink(speaker))
    brain = BrainOrchestrator(model_provider, reminder_scheduler=scheduler)
    console.print("[bold]EVA/EVE Phase 1 text loop[/bold]")
    console.print(
        f"Model provider: [cyan]{type(model_provider).__name__}[/cyan]"
    )
    console.print(
        f"TTS provider: [cyan]{getattr(speaker, 'name', type(speaker).__name__)}[/cyan]"
    )
    console.print("Type a request. Use Ctrl-D or Ctrl-C to exit.")

    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(scheduler.start_async(stop_event))
    exiting = False
    try:
        while True:
            try:
                utterance = await asyncio.to_thread(_blocking_input, "You: ")
            except (EOFError, KeyboardInterrupt):
                print()
                speaker.speak("Standing by.")
                exiting = True
                return

            request = TaskRequest(source="text", utterance=utterance.strip())
            response = await brain.handle(request)
            speaker.speak(response.spoken_summary)
            append_task_log(log_path, request, response.text)
    finally:
        if exiting:
            await _drain_scheduler(scheduler)
        stop_event.set()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except (asyncio.CancelledError, BaseException):  # noqa: BLE001
            pass


async def _drain_scheduler(scheduler: ReminderScheduler) -> None:
    """Wait for any already-scheduled reminders to fire before shutdown.

    Bounded: only waits for jobs whose fire time is within the next 5
    minutes. This keeps short demo reminders working when the user
    quits between scheduling and firing without blocking shutdown
    indefinitely on a long-tailed reminder.
    """
    deadline_extra = 300.0
    next_at = scheduler.next_fire_at()
    if next_at is None:
        return
    import time

    now_monotonic = time.monotonic()
    if next_at - now_monotonic > deadline_extra:
        return
    while True:
        next_at = scheduler.next_fire_at()
        if next_at is None:
            return
        wait_for = next_at - time.monotonic()
        if wait_for > deadline_extra:
            return
        if wait_for > 0:
            await asyncio.sleep(min(wait_for, 0.5))
        else:
            scheduler.run_due()


def _blocking_input(prompt: str) -> str:
    return input(prompt)


DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 8765


def _add_tts_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--tts-provider",
        choices=list(TTS_PROVIDERS),
        default=DEFAULT_TTS_PROVIDER,
        help=(
            "Text-to-speech provider (default: console). "
            "`macos-say` requires macOS; `none` suppresses speech."
        ),
    )
    sub.add_argument(
        "--voice",
        default=None,
        help="Optional voice name passed to the TTS provider (macos-say: -v VOICE).",
    )
    sub.add_argument(
        "--no-speak",
        action="store_true",
        help="Suppress all spoken/printed TTS output regardless of --tts-provider.",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EVA/EVE assistant prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)
    text_parser = subparsers.add_parser("text", help="Run the text-mode voice loop")
    text_parser.add_argument("--log-path", default="data/tasks.jsonl")
    text_parser.add_argument(
        "--model-provider",
        choices=["heuristic", "ollama"],
        default="heuristic",
        help="Model provider to use for answers (default: heuristic)",
    )
    text_parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help=f"Ollama HTTP base URL (default: {DEFAULT_OLLAMA_BASE_URL})",
    )
    text_parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model tag (default: {DEFAULT_OLLAMA_MODEL})",
    )
    _add_tts_arguments(text_parser)

    bridge_parser = subparsers.add_parser(
        "bridge",
        help="Run the local FastAPI bridge (binds 127.0.0.1 by default)",
    )
    bridge_parser.add_argument(
        "--host",
        default=DEFAULT_BRIDGE_HOST,
        help=(
            f"Bind address (default: {DEFAULT_BRIDGE_HOST}). "
            "Do NOT expose the bridge publicly without an auth layer."
        ),
    )
    bridge_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_BRIDGE_PORT,
        help=f"TCP port (default: {DEFAULT_BRIDGE_PORT})",
    )
    bridge_parser.add_argument(
        "--model-provider",
        choices=["heuristic", "ollama"],
        default="heuristic",
        help="Model provider to use for answers (default: heuristic)",
    )
    bridge_parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help=f"Ollama HTTP base URL (default: {DEFAULT_OLLAMA_BASE_URL})",
    )
    bridge_parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model tag (default: {DEFAULT_OLLAMA_MODEL})",
    )
    # The bridge advertises its TTS provider over /capabilities but does not
    # speak server-side today. The flags are accepted so they can flow through
    # to a future server-side voice channel without breaking the CLI surface.
    _add_tts_arguments(bridge_parser)

    voice_parser = subparsers.add_parser(
        "voice",
        help="Run the local push-to-talk voice loop (mic -> STT -> brain -> TTS)",
    )
    voice_parser.add_argument("--log-path", default="data/voice_tasks.jsonl")
    voice_parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_VOICE_DURATION,
        help=f"Recording window per turn in seconds (default: {DEFAULT_VOICE_DURATION})",
    )
    voice_parser.add_argument(
        "--recorder",
        choices=list(RECORDER_PROVIDERS),
        default=DEFAULT_RECORDER,
        help=(
            f"Audio recorder backend (default: {DEFAULT_RECORDER}). "
            "`sounddevice` requires the optional [voice] extra; "
            "`fake` produces silence and is intended for tests/demos."
        ),
    )
    voice_parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f"Capture sample rate in Hz (default: {DEFAULT_SAMPLE_RATE}).",
    )
    voice_parser.add_argument(
        "--stt-provider",
        choices=list(STT_PROVIDERS),
        default=DEFAULT_STT_PROVIDER,
        help=(
            "Speech-to-text provider. `text` returns a fixed string and is the "
            "default for offline/test usage. `whisper-cpp` shells out to a "
            "user-provided whisper.cpp build."
        ),
    )
    voice_parser.add_argument(
        "--whisper-bin",
        default=None,
        help="Path to the whisper.cpp `main` binary (required for whisper-cpp).",
    )
    voice_parser.add_argument(
        "--whisper-model",
        default=None,
        help="Path to a whisper.cpp ggml model file (required for whisper-cpp).",
    )
    voice_parser.add_argument(
        "--silence-timeout",
        type=float,
        default=None,
        help=(
            "Trailing silence (in seconds) that ends a turn for hands-free "
            "dictation. When set, the recorder captures until silence, the "
            "max-duration cap, or manual stop — and the fixed --duration "
            "window is ignored. Default: off (use --duration). Typical: 1.0-1.5."
        ),
    )
    voice_parser.add_argument(
        "--max-duration",
        type=float,
        default=DEFAULT_MAX_DURATION,
        help=(
            "Hard cap on a single turn's recording (seconds), used with "
            f"--silence-timeout. Default: {DEFAULT_MAX_DURATION}. Acts like "
            "the auto-stop on a chat-window mic button so a stuck VAD can't "
            "record forever."
        ),
    )
    voice_parser.add_argument(
        "--silence-threshold",
        type=float,
        default=DEFAULT_SILENCE_THRESHOLD,
        help=(
            "Int16 RMS amplitude below which a chunk is treated as silent "
            f"(default: {DEFAULT_SILENCE_THRESHOLD}). Lower = more sensitive."
        ),
    )
    voice_parser.add_argument(
        "--silence-chunk-seconds",
        type=float,
        default=DEFAULT_CHUNK_SECONDS,
        help=(
            "Polling chunk size for silence detection and manual-stop "
            f"responsiveness (default: {DEFAULT_CHUNK_SECONDS})."
        ),
    )
    voice_parser.add_argument(
        "--mock-utterance",
        default=None,
        help=(
            "When --stt-provider=text, override the fixed transcription "
            "(useful for smoke-testing the brain without a mic)."
        ),
    )
    voice_parser.add_argument(
        "--model-provider",
        choices=["heuristic", "ollama"],
        default="heuristic",
        help="Model provider to use for answers (default: heuristic)",
    )
    voice_parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help=f"Ollama HTTP base URL (default: {DEFAULT_OLLAMA_BASE_URL})",
    )
    voice_parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model tag (default: {DEFAULT_OLLAMA_MODEL})",
    )
    _add_tts_arguments(voice_parser)
    return parser


def run_bridge(
    host: str,
    port: int,
    model_provider: ModelProvider,
    tts_provider_name: str = DEFAULT_TTS_PROVIDER,
) -> None:  # pragma: no cover - thin wrapper around uvicorn
    import uvicorn

    from services.bridge.app import create_app

    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            "[yellow]Warning:[/yellow] binding to non-loopback host "
            f"[bold]{host}[/bold]. The bridge has no auth — exposing it on a "
            "network is unsafe."
        )

    app = create_app(
        model_provider=model_provider,
        tts_provider_name=tts_provider_name,
    )
    console.print(
        f"[bold]EVA bridge[/bold] starting on http://{host}:{port} "
        f"(provider: [cyan]{type(model_provider).__name__}[/cyan], "
        f"tts: [cyan]{tts_provider_name}[/cyan])"
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_voice_command(args) -> None:
    """Build the voice-loop dependencies from parsed CLI args and run it."""
    provider = build_model_provider(
        args.model_provider,
        ollama_base_url=args.ollama_base_url,
        ollama_model=args.ollama_model,
    )
    speaker = build_speaker(
        args.tts_provider,
        voice=args.voice,
        no_speak=args.no_speak,
    )
    try:
        recorder = build_recorder(
            args.recorder,
            sample_rate=args.sample_rate,
        )
    except Exception as exc:
        console.print(f"[red]Failed to initialise recorder:[/red] {exc}")
        raise SystemExit(2) from exc

    try:
        transcriber = build_transcriber(
            args.stt_provider,
            whisper_bin=args.whisper_bin,
            whisper_model=args.whisper_model,
            fixed_text=args.mock_utterance,
        )
    except Exception as exc:
        console.print(f"[red]Failed to initialise transcriber:[/red] {exc}")
        raise SystemExit(2) from exc

    scheduler = ReminderScheduler(sink=build_reminder_sink(speaker))
    brain = BrainOrchestrator(provider, reminder_scheduler=scheduler)
    silence_config: SilenceConfig | None = None
    if args.silence_timeout is not None:
        silence_config = SilenceConfig(
            threshold_rms=args.silence_threshold,
            silence_timeout_seconds=args.silence_timeout,
            max_duration_seconds=args.max_duration,
            chunk_seconds=args.silence_chunk_seconds,
        )

    async def _run_with_scheduler() -> None:
        stop_event = asyncio.Event()
        sched_task = asyncio.create_task(scheduler.start_async(stop_event))
        try:
            await run_voice_loop(
                recorder=recorder,
                transcriber=transcriber,
                brain=brain,
                speaker=speaker,
                duration_seconds=args.duration,
                log_path=Path(args.log_path),
                console=console,
                silence_config=silence_config,
            )
        finally:
            stop_event.set()
            sched_task.cancel()
            try:
                await sched_task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass

    asyncio.run(_run_with_scheduler())


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "text":
        provider = build_model_provider(
            args.model_provider,
            ollama_base_url=args.ollama_base_url,
            ollama_model=args.ollama_model,
        )
        speaker = build_speaker(
            args.tts_provider,
            voice=args.voice,
            no_speak=args.no_speak,
        )
        asyncio.run(run_text_loop(Path(args.log_path), provider, speaker=speaker))
    elif args.command == "bridge":
        provider = build_model_provider(
            args.model_provider,
            ollama_base_url=args.ollama_base_url,
            ollama_model=args.ollama_model,
        )
        # `--no-speak` collapses to the `none` provider for advertising purposes.
        advertised = "none" if args.no_speak else args.tts_provider
        run_bridge(args.host, args.port, provider, tts_provider_name=advertised)
    elif args.command == "voice":
        run_voice_command(args)


if __name__ == "__main__":
    main()
