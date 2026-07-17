"""Baseline offline tests for voice_service (whisper stubbed, no audio/network)."""

import sys
import types

# voice_service imports `whisper` at module top; it is not installed offline.
sys.modules.setdefault("whisper", types.ModuleType("whisper"))
sys.modules["whisper"].load_model = lambda *a, **k: None

import asyncio  # noqa: E402

import voice_service  # noqa: E402


def test_load_profile_returns_dict():
    assert isinstance(voice_service.load_profile(), dict)


def test_route_command_llm_fallback_without_key(monkeypatch):
    # No matching pattern and no LLM key → deterministic offline response.
    monkeypatch.setattr(voice_service, "load_profile", lambda: {})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reply = voice_service.route_command("please tell me a joke about cats")
    assert "no LLM key" in reply


def test_health_endpoint():
    payload = asyncio.run(voice_service.health())
    assert payload["status"] == "ok"
    assert payload["module"] == "voice"
