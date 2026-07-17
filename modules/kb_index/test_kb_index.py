"""Baseline offline tests for kb_index.index_writer (Protocol + Stub, no network)."""

import index_writer as iw


def test_module_imports_clean():
    assert iw.MASTER_INDEX_DOC_ID
    assert hasattr(iw, "append_to_index")


def test_format_row_with_url():
    row = iw.format_row("Title", "a summary", "http://x.y", when="2026-07-17")
    assert row == "• 2026-07-17 — Title: a summary (http://x.y)\n"


def test_format_row_without_url_and_newline_flattened():
    row = iw.format_row("T", "line1\nline2", "", when="2026-01-01")
    assert row == "• 2026-01-01 — T: line1 line2\n"


def test_stub_transport_records_in_memory():
    stub = iw.StubIndexTransport()
    res = stub.append_row("row-a\n")
    assert res["ok"] is True and res["stub"] is True and res["count"] == 1
    stub.append_row("row-b\n")
    assert stub.rows == ["row-a\n", "row-b\n"]


def test_append_to_index_with_injected_stub():
    stub = iw.StubIndexTransport()
    res = iw.append_to_index("Deal", "found one", "http://d", transport=stub, when="2026-07-17")
    assert res["ok"] is True and res["stub"] is True
    assert stub.rows == ["• 2026-07-17 — Deal: found one (http://d)\n"]


def test_make_index_transport_offline_returns_stub(monkeypatch):
    monkeypatch.setattr(iw, "TOKEN_PATH", "/nonexistent/token.pickle")
    monkeypatch.setattr(iw, "CREDS_PATH", "/nonexistent/creds.json")
    assert isinstance(iw.make_index_transport(), iw.StubIndexTransport)
