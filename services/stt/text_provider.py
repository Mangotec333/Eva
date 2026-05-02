from __future__ import annotations

from services.audio.base import AudioClip


class TextTranscriber:
    """Mock transcriber that returns a fixed string.

    Used by tests and offline demos so the voice CLI can be exercised end
    to end without a model or microphone. Optionally accepts a queue of
    utterances so a single instance can simulate a multi-turn conversation
    in tests.
    """

    name = "text"

    def __init__(
        self,
        fixed_text: str = "hello eva",
        utterances: list[str] | None = None,
    ) -> None:
        self.fixed_text = fixed_text
        self._queue = list(utterances) if utterances else []
        self.transcribe_calls: list[AudioClip] = []

    def transcribe(self, clip: AudioClip) -> str:
        self.transcribe_calls.append(clip)
        if self._queue:
            return self._queue.pop(0)
        return self.fixed_text
