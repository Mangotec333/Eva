"""Parser tests for competitor_fetch.parse_cards against REAL page markup.

tests/fixtures/directory_sample.html is a verbatim capture of a live
https://agent.distributedapps.ai/directory results page (2026-07-28). The
parser was originally written without ever seeing the real HTML, so this
fixture is the ground truth that keeps the selectors honest — if the directory
is redesigned, re-capture the fixture and these tests will localise the break.

No network: the fixture is read from disk.
"""

from __future__ import annotations

import os

from competitor_fetch import dedupe_by_url, filter_noise, parse_cards

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "directory_sample.html")


def _fixture_html() -> str:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _parsed() -> list:
    return parse_cards(_fixture_html(), term="real estate", scan_date="2026-07")


def _by_name(entries: list) -> dict:
    return {e.name: e for e in entries}


def test_parses_every_card_on_the_page():
    entries = _parsed()
    assert len(entries) == 9, [e.name for e in entries]
    assert [e.name for e in entries] == [
        "AI Agent Reic",
        "Ava",
        "Gene",
        "Kolena Real Estate AI",
        "Leni",
        "Lucy",
        "Marb.ai",
        "Placy PRO",
        "Strabo",
    ]


def test_ava_fields_read_verbatim():
    ava = _by_name(_parsed())["Ava"]
    assert ava.url == "https://agent.distributedapps.ai/directory/ava"
    assert ava.category == "Personal Assistant"
    assert ava.description == "Your intelligent AI assistant for real estate transactions."
    assert ava.pricing == "Paid"
    assert ava.aivss_score == 8.7


def test_lucy_fields_read_verbatim():
    lucy = _by_name(_parsed())["Lucy"]
    assert lucy.url == "https://agent.distributedapps.ai/directory/lucy"
    assert lucy.category == "Personal Assistant"
    assert lucy.description == (
        "An AI co-pilot for real estate professionals, streamlining tasks like "
        "marketing, transaction forms, and client communication."
    )
    # Pricing is free text, not an enum — this listing says neither Free nor Paid.
    assert lucy.pricing == "contact for pricing"
    assert lucy.aivss_score == 8.6


def test_gene_fields_read_verbatim():
    gene = _by_name(_parsed())["Gene"]
    assert gene.url == "https://agent.distributedapps.ai/directory/gene"
    assert gene.category == "Lead Generation"
    assert gene.description == "AI sales agent for real estate agencies and developers"
    assert gene.pricing == "Free"
    assert gene.aivss_score == 8.6


def test_ampersand_in_description_is_unescaped():
    kolena = _by_name(_parsed())["Kolena Real Estate AI"]
    assert kolena.description == (
        "Automate lease abstractions, cash flow reports & property docs in minutes, not weeks"
    )
    assert kolena.aivss_score == 6.9


def test_every_card_has_the_fields_the_engine_depends_on():
    for entry in _parsed():
        assert entry.name
        assert entry.url.startswith("https://agent.distributedapps.ai/directory/")
        assert entry.category
        assert entry.description
        assert entry.pricing
        assert entry.aivss_score is not None
        assert entry.matched_keyword == "real estate"
        assert entry.first_seen_scan == "2026-07"


def test_aivss_severity_word_and_badge_colour_do_not_leak_into_the_score():
    """Badge text is "AIVSS 9.2 · Critical" with a background hex in the style
    attribute; only the numeric score is captured."""
    marb = _by_name(_parsed())["Marb.ai"]
    assert marb.aivss_score == 9.2
    assert "Critical" not in str(marb.aivss_score)
    assert marb.description == "Real Estate"


def test_pagination_footer_is_not_parsed_as_a_card():
    """The page ends with <div class="dir-page">...9 agents</div>; it must not
    become a tenth entry, and an unexpected pagination shape must not crash."""
    entries = parse_cards(
        _fixture_html().replace("Page 1 of 1 · 9 agents", "Page 2 of 7 · 61 agents"),
        term="real estate",
        scan_date="2026-07",
    )
    assert len(entries) == 9


def test_page_with_no_results_yields_no_entries():
    empty = '<!DOCTYPE html><html><body><div class="dir-grid"></div></body></html>'
    assert parse_cards(empty, term="deal sourcing", scan_date="2026-07") == []


def test_card_missing_a_name_is_skipped():
    html = _fixture_html().replace('<div class="dir-name">Ava</div>', "")
    names = [e.name for e in parse_cards(html, term="real estate", scan_date="2026-07")]
    assert "Ava" not in names
    assert len(names) == 8


def test_dedupe_and_noise_filter_run_on_real_parsed_output():
    """Gene is categorised "Lead Generation" with no deal/M&A/underwriting term of
    its own, so the soft-noise rule drops it. The rest are loose adjacencies."""
    entries = dedupe_by_url(_parsed() + _parsed())
    assert len(entries) == 9

    kept, dropped = filter_noise(entries)
    assert [e.name for e in dropped] == ["Gene"]
    assert len(kept) == 8
