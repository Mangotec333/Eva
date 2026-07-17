"""Baseline offline tests for linkedin post credential loading (no network)."""

import json
import os
import tempfile

import pytest

import post


def test_load_credentials_missing_config_exits(monkeypatch):
    monkeypatch.setattr(post, "CONFIG_PATH", "/nonexistent/channels_config.json")
    with pytest.raises(SystemExit):
        post.load_credentials()


def test_load_credentials_returns_token_and_urn(monkeypatch):
    tmp = os.path.join(tempfile.mkdtemp(), "channels_config.json")
    with open(tmp, "w") as f:
        json.dump({"linkedin": {"access_token": "tok123", "person_urn": "urn:li:person:XYZ"}}, f)
    monkeypatch.setattr(post, "CONFIG_PATH", tmp)
    token, urn = post.load_credentials()
    assert token == "tok123"
    assert urn == "urn:li:person:XYZ"


def test_load_credentials_incomplete_config_exits(monkeypatch):
    tmp = os.path.join(tempfile.mkdtemp(), "channels_config.json")
    with open(tmp, "w") as f:
        json.dump({"linkedin": {"access_token": "tok-only"}}, f)
    monkeypatch.setattr(post, "CONFIG_PATH", tmp)
    with pytest.raises(SystemExit):
        post.load_credentials()
