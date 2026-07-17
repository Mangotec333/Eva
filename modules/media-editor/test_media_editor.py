"""Baseline offline tests for media-editor (state client stub + pure helpers)."""

import asyncio

import state_client
import main


def test_stub_state_client_records_events():
    stub = state_client.StubStateLedgerClient()
    res = stub.emit(event_type="media.edit.queued", summary="hi", entity_id="job1")
    assert res["ok"] is True and res["stub"] is True
    assert stub.events[0]["event_type"] == "media.edit.queued"


def test_build_state_client_offline_returns_stub():
    assert isinstance(state_client.build_state_client(offline=True),
                      state_client.StubStateLedgerClient)


def test_escape_drawtext_escapes_dangerous_chars():
    out = main._escape_drawtext("a'b:c\\d")
    assert "\\'" in out and "\\:" in out and "\\\\" in out


def test_db_to_linear_zero_db_is_unity():
    assert abs(main._db_to_linear(0) - 1.0) < 1e-9


def test_normalize_options_defaults_and_types():
    opts = main._normalize_options({})
    assert opts["caption_left"] == main.DEFAULT_CAPTION_LEFT
    assert opts["caption_right"] == main.DEFAULT_CAPTION_RIGHT
    assert opts["accent_hex"] == main.DEFAULT_ACCENT_HEX
    assert opts["music_path"] is None
    assert isinstance(opts["music_duck_db"], (int, float))


def test_normalize_options_bad_duck_falls_back():
    opts = main._normalize_options({"music_duck_db": "not-a-number"})
    assert opts["music_duck_db"] == main.DEFAULT_MUSIC_DUCK_DB


def test_health_endpoint_returns_ok():
    payload = asyncio.run(main.health_check())
    assert payload["status"] == "ok"
    assert payload["module"] == "eva-media-editor"
