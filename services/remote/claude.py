"""Claude / Anthropic remote-client abstraction — the REASONING brain.

Where ``perplexity.py`` is the seam for the *research / orchestration*
brain (Perplexity Computer), this module is the seam for the *reasoning*
brain: Anthropic's Claude. EVA's agent loops call ``complete()`` for the
judgement layer that sits ON TOP of a deterministic core — edge-case
rationale, lever assessments, confidence flags.

Design notes
------------
- Transport is stdlib ``urllib`` only, so no new dependency is required
  (``httpx`` may not be installed in every runtime). Network is wrapped
  in ``try/except`` and always returns a structured dict — callers never
  see a raw exception.
- The API key is read from the environment (``ANTHROPIC_API_KEY``) or an
  optional config path. It is NEVER hardcoded.
- ``NoopClaudeClient`` mirrors ``NoopPerplexityClient``: when no key is
  configured it returns a safe ``no_api_key`` result so the agent loop
  degrades to its deterministic core instead of crashing.
- The interface is messages-style to match the Anthropic Messages API:
  ``complete(system, messages, max_tokens, model) -> {content, stop_reason, usage}``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_S = 60

# Message = {"role": "user" | "assistant", "content": str}
Message = dict[str, Any]


@runtime_checkable
class ClaudeClient(Protocol):
    """Transport-agnostic interface for the Claude reasoning brain.

    A concrete HTTP client implements this Protocol; tests inject the
    :class:`NoopClaudeClient` so no key or network is needed.
    """

    def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model: str = DEFAULT_MODEL,
    ) -> dict[str, Any]:
        """Send a system prompt + message list, return a result envelope.

        Returns a dict with at least::

            {
              "content": str,          # assistant text (flattened)
              "stop_reason": str|None,
              "usage": {"input_tokens": int, "output_tokens": int},
              "error": str|None,       # present only on failure
            }
        """


def _result(
    content: str = "",
    stop_reason: str | None = None,
    usage: dict[str, int] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Uniform result envelope so every code path returns the same shape."""
    return {
        "content": content,
        "stop_reason": stop_reason,
        "usage": usage or {"input_tokens": 0, "output_tokens": 0},
        "error": error,
    }


def resolve_api_key(config_path: str | None = None) -> str | None:
    """Resolve the Anthropic API key from env, then an optional config file.

    Order: ``ANTHROPIC_API_KEY`` env var wins. Otherwise, if ``config_path``
    is given and exists, read a single-line key (or a ``key=value`` /
    JSON ``{"ANTHROPIC_API_KEY": ...}`` form) from it. Returns ``None`` when
    no key can be found — callers should degrade to Noop behaviour.
    """
    env = os.environ.get("ANTHROPIC_API_KEY")
    if env:
        return env.strip()
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
        except OSError:
            return None
        if not raw:
            return None
        if raw.startswith("{"):
            try:
                return (json.loads(raw).get("ANTHROPIC_API_KEY") or "").strip() or None
            except json.JSONDecodeError:
                return None
        if "=" in raw.splitlines()[0]:
            return raw.splitlines()[0].split("=", 1)[1].strip().strip('"') or None
        return raw.splitlines()[0].strip() or None
    return None


class NoopClaudeClient:
    """Default client used when no Anthropic key/transport is configured.

    Always returns a structured ``no_api_key`` result. The agent loop treats
    this as a safe degrade: the deterministic scoring core still runs and the
    advisory layer is simply empty (tokens=0) rather than the loop crashing.
    """

    def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model: str = DEFAULT_MODEL,
    ) -> dict[str, Any]:
        return _result(
            content="",
            stop_reason="no_api_key",
            error="no_api_key",
        )


class HttpxClaudeClient:
    """Real Anthropic Messages transport over stdlib ``urllib``.

    Despite the name (kept for parity with the ``Httpx*`` transport naming
    convention in the codebase), this uses ``urllib`` so it adds no new
    dependency. All network failures are caught and returned as an ``error``
    envelope; the client never raises to its caller.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        config_path: str | None = None,
        base_url: str = ANTHROPIC_API_URL,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key or resolve_api_key(config_path)
        self._base_url = base_url
        self._timeout_s = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model: str = DEFAULT_MODEL,
    ) -> dict[str, Any]:
        if not self._api_key:
            # Degrade exactly like the Noop client rather than attempting a
            # doomed request without credentials.
            return _result(stop_reason="no_api_key", error="no_api_key")

        payload = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            self._base_url,
            data=payload,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
            return _result(stop_reason="http_error", error=f"http_{exc.code}: {detail[:500]}")
        except urllib.error.URLError as exc:
            return _result(stop_reason="network_error", error=f"network_error: {exc.reason}")
        except (TimeoutError, json.JSONDecodeError, OSError) as exc:
            return _result(stop_reason="transport_error", error=f"transport_error: {exc}")

        return _result(
            content=_flatten_content(body.get("content", [])),
            stop_reason=body.get("stop_reason"),
            usage=body.get("usage") or {"input_tokens": 0, "output_tokens": 0},
        )


def _flatten_content(blocks: Any) -> str:
    """Flatten Anthropic content blocks into a single text string."""
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    return "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    )


def make_claude_client(config_path: str | None = None) -> ClaudeClient:
    """Return the real client when a key resolves, else the safe Noop client.

    This is the factory callers should prefer: it never raises and always
    yields something implementing :class:`ClaudeClient`.
    """
    if resolve_api_key(config_path):
        return HttpxClaudeClient(config_path=config_path)
    return NoopClaudeClient()


def total_tokens(usage: dict[str, int] | None) -> int:
    """Sum input + output tokens from a usage dict (0 when absent)."""
    usage = usage or {}
    return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
