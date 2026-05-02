from __future__ import annotations

import pytest

from services.model.ollama import OllamaProvider
from services.model.provider import HeuristicModelProvider
from services.voice.cli import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    build_arg_parser,
    build_model_provider,
)


def test_build_model_provider_defaults_to_heuristic() -> None:
    provider = build_model_provider("heuristic")
    assert isinstance(provider, HeuristicModelProvider)


def test_build_model_provider_returns_ollama_when_selected() -> None:
    provider = build_model_provider(
        "ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2",
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "llama3.2"


def test_build_model_provider_strips_trailing_slash() -> None:
    provider = build_model_provider(
        "ollama",
        ollama_base_url="http://example.com:11434/",
        ollama_model="mistral",
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://example.com:11434"
    assert provider.model == "mistral"


def test_build_model_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown model provider"):
        build_model_provider("gpt5")


def test_cli_parses_text_defaults() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["text"])
    assert args.command == "text"
    assert args.model_provider == "heuristic"
    assert args.ollama_base_url == DEFAULT_OLLAMA_BASE_URL
    assert args.ollama_model == DEFAULT_OLLAMA_MODEL
    assert args.log_path == "data/tasks.jsonl"


def test_cli_parses_ollama_options() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "text",
            "--model-provider",
            "ollama",
            "--ollama-base-url",
            "http://127.0.0.1:11434",
            "--ollama-model",
            "llama3.2",
        ]
    )
    assert args.model_provider == "ollama"
    assert args.ollama_base_url == "http://127.0.0.1:11434"
    assert args.ollama_model == "llama3.2"


def test_cli_rejects_invalid_model_provider() -> None:
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["text", "--model-provider", "bogus"])


def test_cli_to_provider_wiring_for_ollama() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "text",
            "--model-provider",
            "ollama",
            "--ollama-base-url",
            "http://10.0.0.5:11434",
            "--ollama-model",
            "qwen2.5",
        ]
    )
    provider = build_model_provider(
        args.model_provider,
        ollama_base_url=args.ollama_base_url,
        ollama_model=args.ollama_model,
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://10.0.0.5:11434"
    assert provider.model == "qwen2.5"


def test_cli_to_provider_wiring_for_heuristic_default() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["text"])
    provider = build_model_provider(
        args.model_provider,
        ollama_base_url=args.ollama_base_url,
        ollama_model=args.ollama_model,
    )
    assert isinstance(provider, HeuristicModelProvider)


def test_cli_parses_bridge_defaults() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["bridge"])
    assert args.command == "bridge"
    assert args.host == DEFAULT_BRIDGE_HOST
    assert args.host == "127.0.0.1"
    assert args.port == DEFAULT_BRIDGE_PORT
    assert args.model_provider == "heuristic"


def test_cli_parses_bridge_with_ollama_flags() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "bridge",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--model-provider",
            "ollama",
            "--ollama-base-url",
            "http://127.0.0.1:11434",
            "--ollama-model",
            "llama3.2",
        ]
    )
    assert args.port == 9000
    assert args.model_provider == "ollama"
    assert args.ollama_model == "llama3.2"
