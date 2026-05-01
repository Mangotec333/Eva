from __future__ import annotations

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    @abstractmethod
    async def answer(self, prompt: str) -> str:
        raise NotImplementedError


class HeuristicModelProvider(ModelProvider):
    async def answer(self, prompt: str) -> str:
        cleaned = prompt.strip()
        if not cleaned:
            return "I am listening."
        return (
            "EVA Phase 1 is online in text mode. "
            f"I heard: {cleaned}. "
            "Next, connect Ollama for local model responses."
        )

