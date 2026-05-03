"""Sanity checks that the operator-confirmed decisions are documented.

These tests are intentionally lightweight: they only verify that the
recorded decisions live in the design doc / config so they are not
silently dropped in a future edit. They do not assert prose wording.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "hybrid-architecture.md"
EXAMPLE_CONFIG = ROOT / "config" / "eva.example.yaml"


def test_design_doc_records_organizer_first_decision() -> None:
    text = SPEC.read_text()
    assert "Recorded decisions" in text
    assert "request organizer" in text.lower() or "organizer" in text.lower()


def test_design_doc_records_ava_wake_phrase() -> None:
    assert "AVA" in SPEC.read_text()


def test_design_doc_records_default_ollama_model() -> None:
    assert "llama3.2" in SPEC.read_text()


def test_design_doc_records_adapter_priority_order() -> None:
    import re

    text = SPEC.read_text().lower()
    section = re.sub(r"\s+", " ", text.split("recorded decisions", 1)[-1])
    files_idx = section.find("local files")
    shell_idx = section.find("shell command")
    browser_idx = section.find("browser automation")
    assert 0 <= files_idx < shell_idx < browser_idx


def test_default_config_uses_llama32() -> None:
    assert "llama3.2" in EXAMPLE_CONFIG.read_text()


def test_design_doc_keeps_perplexity_as_primary_remote() -> None:
    text = SPEC.read_text()
    assert "Perplexity Computer is EVA's primary remote horsepower layer" in text
