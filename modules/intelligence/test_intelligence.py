"""Baseline offline tests for intelligence landing_tracker renderers (no network)."""

import landing_tracker as lt


def _sample_report():
    return {
        "generated_at": "2026-07-17T00:00:00+00:00",
        "base_url": lt.BASE_URL,
        "ghl_offline": True,
        "landing": [
            {"name": "Home", "path": "/", "url": "u", "live": True, "status": 200, "error": None},
            {"name": "Digest", "path": "/digest", "url": "u", "live": False, "status": None, "error": "timeout"},
        ],
        "magnets": [
            {"label": "Whitepaper", "tag": "eva-magnet-whitepaper", "count": 3, "ok": True},
            {"label": "Digest", "tag": "eva-magnet-digest", "count": None, "ok": False},
        ],
        "total": {"tag": lt.TOTAL_TAG, "count": 3, "ok": True},
        "summary": {"pages_live": 1, "pages_total": 2, "total_leads": 3},
    }


def test_count_str_handles_none():
    assert lt._count_str(None) == "—"
    assert lt._count_str(5) == "5"


def test_render_text_block():
    out = lt.render_text(_sample_report())
    assert "LANDING + INTEREST" in out
    assert "Pages: 1/2 live" in out
    assert "DOWN: Digest" in out


def test_render_human_block():
    out = lt.render_human(_sample_report())
    assert "EVA LANDING + INTEREST" in out
    assert "Whitepaper" in out
