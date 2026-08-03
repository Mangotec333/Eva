"""
Call-capture — summarization client (behind a Protocol)

Turns a raw Transcript into a CallSummary: summary text, action items,
key topics, sentiment. Same Protocol/Http/Stub pattern as the rest of Eva.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Protocol, runtime_checkable

from models import CallSummary, Transcript

logger = logging.getLogger("eva.call_capture.summarizer")

LLM_API_BASE = "https://api.openai.com/v1"

SUMMARY_PROMPT = """You are summarizing a business call transcript for a CRM note.
Return strict JSON with keys: summary (2-4 sentences), action_items (list of
short strings), key_topics (list of short strings), sentiment (one of
"positive", "neutral", "negative").

Transcript:
{transcript}
"""


@runtime_checkable
class SummarizerClient(Protocol):
    def summarize(self, transcript: Transcript) -> CallSummary: ...


class SummarizerError(RuntimeError):
    pass


class StubSummarizerClient:
    """Offline, deterministic — naive keyword extraction, no network."""

    ACTION_VERBS = ("call", "send", "follow up", "set up", "schedule", "review")

    def summarize(self, transcript: Transcript) -> CallSummary:
        text = transcript.full_text
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        summary = " ".join(sentences[:2]) if sentences else text[:200]

        action_items = [
            s for s in sentences
            if any(v in s.lower() for v in self.ACTION_VERBS)
        ] or ["Follow up on this call"]

        topics = []
        for kw in ("mission villa", "seller", "financing", "carry", "refinance",
                   "capital", "deal", "price"):
            if kw in text.lower():
                topics.append(kw)

        negative_words = ("problem", "issue", "concern", "won't", "can't", "no deal")
        positive_words = ("great", "agree", "yes", "excited", "let's move")
        low = text.lower()
        if any(w in low for w in negative_words):
            sentiment = "negative"
        elif any(w in low for w in positive_words):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        return CallSummary(
            summary=summary,
            action_items=action_items[:5],
            key_topics=topics or ["general"],
            sentiment=sentiment,
        )


class HttpLLMSummarizer:
    """Real client — calls an OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: str = LLM_API_BASE,
                 model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.model = model
        try:
            import httpx  # noqa: F401
            self._httpx_available = True
        except ImportError:
            self._httpx_available = False

    def summarize(self, transcript: Transcript) -> CallSummary:
        if not self.api_key:
            raise SummarizerError("No LLM_API_KEY/OPENAI_API_KEY configured")
        if not self._httpx_available:
            raise SummarizerError("httpx not installed — cannot make live summarization calls")

        import httpx

        prompt = SUMMARY_PROMPT.format(transcript=transcript.full_text)
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        resp = httpx.post(f"{self.base_url}/chat/completions",
                          headers=headers, json=body, timeout=60.0)
        if resp.status_code >= 400:
            raise SummarizerError(f"LLM API {resp.status_code}: {resp.text[:300]}")

        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return CallSummary(
            summary=parsed.get("summary", ""),
            action_items=parsed.get("action_items", []),
            key_topics=parsed.get("key_topics", []),
            sentiment=parsed.get("sentiment", "neutral"),
        )


def build_summarizer_client(*, use_stub: Optional[bool] = None) -> SummarizerClient:
    if use_stub is None:
        use_stub = not bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    if use_stub:
        return StubSummarizerClient()
    return HttpLLMSummarizer()
