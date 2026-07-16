"""
EVA GHL Agent — OAuth token provider tests (OFFLINE / mocked, zero network).

Covers the OAuth rewrite: refresh flow, in-memory + sqlite caching, preemptive
refresh, the 401 → force-refresh → retry loop (and the ghl_oauth_failed emission
on a persistent 401), the static ``GHL_ACCESS_TOKEN`` fallback with its
deprecation warning, and fully offline (mocked) mode.

No real GHL / OAuth calls: the token poster and the client transport are both
injected fakes.

Run:  python -m pytest modules/ghl-agent/tests/test_oauth.py
"""

from __future__ import annotations

import logging
import os

import pytest

os.environ["EVA_GHL_OFFLINE"] = "1"

import memory
import oauth
from ghl_client import HttpGHLClient
from oauth import GHLOAuthError, GHLTokenProvider, build_token_provider
from state_client import StubStateLedgerClient


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "ghl_agent.db")
    memory.init_db(path)
    return path


CONFIG = {
    "client_id": "cid",
    "client_secret": "csecret",
    "refresh_token": "rtoken",
    "location_id": "loc123",
}


def _poster(tokens, calls):
    """Return a token_poster that yields the given access tokens in order."""
    def poster(url, fields):
        calls.append(fields)
        i = min(len(calls) - 1, len(tokens) - 1)
        return {"access_token": tokens[i], "expires_in": 3600,
                "refresh_token": fields["refresh_token"]}
    return poster


# ---------------------------------------------------------------------------
# Refresh flow
# ---------------------------------------------------------------------------

def test_refresh_flow_returns_access_token(db):
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1"], calls))
    token = prov.get_access_token()
    assert token == "tok-1"
    assert len(calls) == 1
    # The refresh sent the refresh-token grant with our creds.
    assert calls[0]["grant_type"] == "refresh_token"
    assert calls[0]["client_id"] == "cid"
    assert calls[0]["refresh_token"] == "rtoken"


def test_refresh_raises_when_no_access_token(db):
    def bad_poster(url, fields):
        return {"expires_in": 3600}  # missing access_token
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=bad_poster)
    with pytest.raises(GHLOAuthError):
        prov.get_access_token()


def test_refresh_raises_without_refresh_token(db):
    cfg = {**CONFIG, "refresh_token": ""}
    prov = GHLTokenProvider(cfg, db_path=db, token_poster=_poster(["x"], []))
    with pytest.raises(GHLOAuthError):
        prov.force_refresh()


# ---------------------------------------------------------------------------
# Caching + expiry
# ---------------------------------------------------------------------------

def test_token_is_cached_in_memory(db):
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1"], calls))
    prov.get_access_token()
    prov.get_access_token()
    prov.get_access_token()
    # Only the first call hit the token endpoint.
    assert len(calls) == 1


def test_token_persisted_to_sqlite_survives_new_provider(db):
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1"], calls))
    prov.get_access_token()
    # A brand-new provider (simulating a restart) loads the cached token.
    prov2 = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-2"], calls))
    assert prov2.get_access_token() == "tok-1"
    assert len(calls) == 1  # no extra refresh — cache hit from sqlite


def test_expired_token_triggers_refresh(db):
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1", "tok-2"], calls))
    prov.get_access_token()
    # Force the cached token past its expiry.
    prov._expiry_ts = 0
    assert prov.get_access_token() == "tok-2"
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Preemptive refresh (<60s left)
# ---------------------------------------------------------------------------

def test_preemptive_refresh_when_near_expiry(db):
    import time
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1", "tok-2"], calls))
    prov.get_access_token()
    # Leave only 30s — inside the 60s preemptive window.
    prov._expiry_ts = time.time() + 30
    assert prov.get_access_token() == "tok-2"
    assert len(calls) == 2


def test_no_refresh_when_plenty_of_time_left(db):
    import time
    calls: list[dict] = []
    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=_poster(["tok-1"], calls))
    prov.get_access_token()
    prov._expiry_ts = time.time() + 600  # well outside the window
    prov.get_access_token()
    assert len(calls) == 1


def test_rotated_refresh_token_is_persisted_and_used(db):
    calls: list[dict] = []

    def rotating_poster(url, fields):
        calls.append(fields)
        # GHL hands back a new refresh token each time.
        return {"access_token": f"tok-{len(calls)}", "expires_in": 3600,
                "refresh_token": f"rtoken-{len(calls)}"}

    prov = GHLTokenProvider(CONFIG, db_path=db, token_poster=rotating_poster)
    prov.force_refresh()
    prov.force_refresh()
    # Second refresh used the rotated token from the first response.
    assert calls[1]["refresh_token"] == "rtoken-1"


# ---------------------------------------------------------------------------
# 401 → force refresh → retry once  (client integration)
# ---------------------------------------------------------------------------

def _client_with_provider(db, state=None):
    prov = GHLTokenProvider(CONFIG, db_path=db, offline=True)
    return HttpGHLClient(token_provider=prov, state=state, location_id="loc123")


def test_401_triggers_refresh_and_retry_success(db):
    client = _client_with_provider(db)
    seq = [
        {"ok": False, "status": 401},        # first attempt: unauthorized
        {"ok": True, "status": 200, "items": []},  # after refresh: success
    ]
    sent: list[tuple] = []

    def fake_send(method, url, *, params=None, body=None):
        sent.append((method, url))
        return seq[len(sent) - 1]

    client._send = fake_send
    result = client._request("GET", "/opportunities/pipelines")
    assert result["ok"] is True
    assert len(sent) == 2  # retried exactly once


def test_persistent_401_emits_ghl_oauth_failed(db):
    state = StubStateLedgerClient()
    client = _client_with_provider(db, state=state)

    def always_401(method, url, *, params=None, body=None):
        return {"ok": False, "status": 401}

    client._send = always_401
    result = client._request("GET", "/opportunities/pipelines")
    assert result["status"] == 401
    assert any(e["event_type"] == "ghl_oauth_failed" for e in state.events)


def test_persistent_401_does_not_crash_without_state(db):
    client = _client_with_provider(db, state=None)
    client._send = lambda *a, **k: {"ok": False, "status": 401}
    # Must return the 401 honestly, never raise.
    assert client._request("GET", "/x")["status"] == 401


# ---------------------------------------------------------------------------
# Static GHL_ACCESS_TOKEN fallback (deprecation warning)
# ---------------------------------------------------------------------------

def test_build_token_provider_none_without_oauth(monkeypatch):
    monkeypatch.setattr(oauth, "load_oauth_config",
                        lambda: {"client_id": "", "client_secret": "",
                                 "refresh_token": "", "location_id": "loc"})
    assert build_token_provider(offline=False) is None


def test_static_token_fallback_logs_deprecation(db, caplog):
    # No token provider → static-token path → deprecation warning at init.
    with caplog.at_level(logging.WARNING, logger="eva.ghl.client"):
        client = HttpGHLClient(token_provider=None, access_token="pit-static-123")
    assert client._current_token() == "pit-static-123"
    assert any("deprecated" in r.message.lower() for r in caplog.records)


def test_static_token_fallback_requires_a_token():
    from ghl_client import GHLAuthError
    with pytest.raises(GHLAuthError):
        HttpGHLClient(token_provider=None, access_token="")


# ---------------------------------------------------------------------------
# Offline (mocked) mode
# ---------------------------------------------------------------------------

def test_offline_provider_issues_mock_token_without_network(db):
    def exploding_poster(url, fields):
        raise AssertionError("offline mode must not hit the network")
    prov = GHLTokenProvider(CONFIG, db_path=db, offline=True,
                            token_poster=exploding_poster)
    assert prov.get_access_token() == "offline-mock-access-token"


def test_build_token_provider_offline_is_mocked(db):
    prov = build_token_provider(offline=True, db_path=db)
    assert prov is not None
    assert prov.get_access_token() == "offline-mock-access-token"
