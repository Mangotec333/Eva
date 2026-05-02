from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Speaker(Protocol):
    """Minimal text-to-speech interface used by the EVA voice loop."""

    def speak(self, text: str) -> None:
        ...
