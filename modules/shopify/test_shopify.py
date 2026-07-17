"""Baseline offline tests for shopify oauth handler (hmac + health, no network)."""

import hashlib
import hmac as hmac_mod
import os

# oauth_handler raises at import unless these are present — set dummy values.
os.environ.setdefault("SHOPIFY_CLIENT_ID", "test-client-id")
os.environ.setdefault("SHOPIFY_CLIENT_SECRET", "test-client-secret")

import asyncio  # noqa: E402

import oauth_handler  # noqa: E402


def _sign(params: dict, secret: str) -> str:
    payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac_mod.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_verify_hmac_accepts_valid_signature():
    secret = "shhh-secret"
    params = {"shop": "x.myshopify.com", "code": "abc123"}
    signed = dict(params, hmac=_sign(params, secret))
    assert oauth_handler.verify_hmac(signed, secret) is True


def test_verify_hmac_rejects_bad_signature():
    params = {"shop": "x.myshopify.com", "code": "abc123", "hmac": "deadbeef"}
    assert oauth_handler.verify_hmac(params, "shhh-secret") is False


def test_verify_hmac_rejects_missing_hmac():
    assert oauth_handler.verify_hmac({"shop": "x.myshopify.com"}, "s") is False


def test_health_endpoint():
    payload = asyncio.run(oauth_handler.health())
    assert payload["status"] == "ok"
    assert payload["service"] == "shopify-oauth"
