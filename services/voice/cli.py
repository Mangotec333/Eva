from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console

from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import TaskRequest
from services.model.provider import HeuristicModelProvider
from services.tts.console import ConsoleSpeaker

console = Console()


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


async def run_text_loop(log_path: Path) -> None:
    brain = BrainOrchestrator(HeuristicModelProvider())
    speaker = ConsoleSpeaker()
    console.print("[bold]EVA/EVE Phase 1 text loop[/bold]")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="EVA/EVE assistant prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)
    text_parser = subparsers.add_parser("text", help="Run the text-mode voice loop")
    text_parser.add_argument("--log-path", default="data/tasks.jsonl")
    args = parser.parse_args()

    if args.command == "text":
        asyncio.run(run_text_loop(Path(args.log_path)))


if __name__ == "__main__":
    main()

