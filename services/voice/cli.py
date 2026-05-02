from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console

from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import TaskRequest
from services.model.ollama import OllamaProvider
from services.model.provider import HeuristicModelProvider, ModelProvider
from services.tts import TTS_PROVIDERS, Speaker, build_speaker

console = Console()

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_TTS_PROVIDER = "console"


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


async def run_text_loop(
    log_path: Path,
    model_provider: ModelProvider,
    speaker: Speaker | None = None,
) -> None:
    brain = BrainOrchestrator(model_provider)
    speaker = speaker or build_speaker(DEFAULT_TTS_PROVIDER)
    console.print("[bold]EVA/EVE Phase 1 text loop[/bold]")
    console.print(
        f"Model provider: [cyan]{type(model_provider).__name__}[/cyan]"
    )
    console.print(
        f"TTS provider: [cyan]{getattr(speaker, 'name', type(speaker).__name__)}[/cyan]"
    )
    console.print("Type a request. Use Ctrl-D or Ctrl-C to exit.")

    while True:
        try:
            utterance = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            speaker.speak("Standing by.")
            return

        request = TaskRequest(source="text", utterance=utterance)
        response = await brain.handle(request)
        speaker.speak(response.spoken_summary)
        append_task_log(log_path, request, response.text)


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


if __name__ == "__main__":
    main()
