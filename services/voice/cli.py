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
from services.tts.console import ConsoleSpeaker

console = Console()

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


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


async def run_text_loop(log_path: Path, model_provider: ModelProvider) -> None:
    brain = BrainOrchestrator(model_provider)
    speaker = ConsoleSpeaker()
    console.print("[bold]EVA/EVE Phase 1 text loop[/bold]")
    console.print(
        f"Model provider: [cyan]{type(model_provider).__name__}[/cyan]"
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
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "text":
        provider = build_model_provider(
            args.model_provider,
            ollama_base_url=args.ollama_base_url,
            ollama_model=args.ollama_model,
        )
        asyncio.run(run_text_loop(Path(args.log_path), provider))


if __name__ == "__main__":
    main()
