"""Baseline offline tests for content-engine voice_dna + generator (no LLM/network)."""

import os

import voice_dna
import generator


def test_voice_dna_imports_and_prompt_present():
    assert isinstance(voice_dna.VOICE_SYSTEM_PROMPT, str)
    assert voice_dna.VOICE_SYSTEM_PROMPT.strip()


def test_check_banned_words_flags_known_banned():
    banned = voice_dna._profile.get("voice", {}).get("banned_words", [])
    assert banned, "expected a non-empty banned_words list in the loaded profile"
    sample = banned[0]
    found = voice_dna.check_banned_words(f"This is a {sample} sentence.")
    assert sample in [w.lower() for w in found] or sample in found


def test_check_banned_words_clean_text():
    assert voice_dna.check_banned_words("A perfectly ordinary sentence.") == []


def test_build_system_prompt_returns_str():
    prompt = voice_dna.build_system_prompt(voice_dna.load_profile())
    assert isinstance(prompt, str) and prompt.strip()


def test_generate_drafts_template_fallback(monkeypatch):
    # Ensure no API key so generation falls back to templates (zero network).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    drafts = generator.generate_drafts("Shipped the scoring engine", ["linkedin"], 2, "activity")
    assert isinstance(drafts, list) and len(drafts) == 2
    for d in drafts:
        assert d["platform"] == "linkedin"
        assert d["draft_text"].strip()
        assert d["status"] == "draft"
        assert "id" in d


def test_pick_insight_returns_str():
    assert isinstance(generator._pick_insight("did things this week"), str)
