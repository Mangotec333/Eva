from __future__ import annotations


class ConsoleSpeaker:
    """Default offline-safe speaker that prints to stdout.

    Used as the default in tests and on non-macOS hosts so the text loop
    runs anywhere without external dependencies.
    """

    name = "console"

    def speak(self, text: str) -> None:
        print(f"EVA: {text}")
