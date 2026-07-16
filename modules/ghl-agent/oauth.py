"""
EVA GHL Agent — GoHighLevel OAuth 2.0 token provider
====================================================

Replaces the static ``pit-`` access token with a self-refreshing OAuth token so
Eva never rotates a token by hand again. This is the single seam that turns a
long-lived ``refresh_token`` into a short-lived ``access_token`` for every GHL
call.

## How it works

- **Config (config-file-primary).** Credentials come from
  ``~/.eva/channels_config.json`` under the ``ghl.oauth`` section
  (``client_id``, ``client_secret``, ``refresh_token``, ``location_id``), with an
  env-var fallback (``GHL_OAUTH_CLIENT_ID`` …). This mirrors the
  ``social-publish/credentials.build_cfg()`` config-file-primary pattern.
- **Refresh.** ``POST https://services.leadconnectorhq.com/oauth/token`` with
  ``grant_type=refresh_token`` returns ``{access_token, expires_in, ...}``. The
  access token + absolute expiry are cached in memory AND in the module's SQLite
  (via ``memory`` key/value) so a restart doesn't force a refresh. GHL rotates
  refresh tokens, so a returned ``refresh_token`` is persisted and preferred over
  the config one on the next refresh.
- **Preemptive refresh.** ``get_access_token()`` refreshes when fewer than
  ``PREEMPTIVE_REFRESH_SECONDS`` (60s) remain, so calls never race the expiry.
- **Resilient.** Every refresh is wrapped: a failure is logged and raised as
  ``GHLOAuthError`` for the caller to handle (the GHL client catches it and
  degrades) — the process never crashes.
- **Offline-safe.** ``EVA_GHL_OFFLINE=1`` (or ``offline=True``) returns a mocked
  token with no network, so tests and the sandbox are fully self-contained.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import memory

logger = logging.getLogger("eva.ghl.oauth")

# GHL / LeadConnector OAuth token endpoint.
OAUTH_TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
# Refresh when fewer than this many seconds remain on the cached token.
PREEMPTIVE_REFRESH_SECONDS = 60
# Default location for the Eva Acquisition sub-account.
DEFAULT_LOCATION_ID = "kyK4yAY6Hur3F4deCx2n"

# Same source the channels connectors + social-publish read from.
CHANNELS_CONFIG_PATH = Path.home() / ".eva" / "channels_config.json"

# Env fallbacks (config file is primary; these fill any blanks).
OAUTH_ENV = {
    "client_id": "GHL_OAUTH_CLIENT_ID",
    "client_secret": "GHL_OAUTH_CLIENT_SECRET",
    "refresh_token": "GHL_OAUTH_REFRESH_TOKEN",
    "location_id": "GHL_LOCATION_ID",
}

# SQLite key/value keys (persisted in the module's ghl_agent.db via ``memory``).
_TOKEN_CACHE_KEY = "ghl_oauth_access_token"
_REFRESH_CACHE_KEY = "ghl_oauth_refresh_token"


class GHLOAuthError(RuntimeError):
    """A GHL OAuth refresh failed (network, bad creds, or bad response)."""


# ---------------------------------------------------------------------------
# Config (config-file-primary, mirrors social-publish/credentials.build_cfg)
# ---------------------------------------------------------------------------

def _load_channels_config() -> dict:
    try:
        with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, ValueError):
        return {}


def load_oauth_config() -> dict:
    """Return the ``ghl.oauth`` creds: config-file first, then env fallback.

    Shape: ``{client_id, client_secret, refresh_token, location_id}``. Missing
    values are empty strings; ``location_id`` defaults to the Eva sub-account.
    """
    section = ((_load_channels_config().get("ghl") or {}).get("oauth") or {})
    out: dict[str, str] = {}
    for field, env_name in OAUTH_ENV.items():
        raw = section.get(field)
        val = raw.strip() if isinstance(raw, str) else raw
        if not val:
            val = os.environ.get(env_name, "").strip()
        out[field] = val or ""
    if not out["location_id"]:
        out["location_id"] = DEFAULT_LOCATION_ID
    return out


def has_oauth_config(cfg: Optional[dict] = None) -> bool:
    """True when the three refresh-flow creds are all present."""
    cfg = cfg if cfg is not None else load_oauth_config()
    return bool(cfg.get("client_id") and cfg.get("client_secret")
                and cfg.get("refresh_token"))


# ---------------------------------------------------------------------------
# Token provider
# ---------------------------------------------------------------------------

# A token poster is (url, form_fields) -> parsed-json-dict. Injectable for tests.
TokenPoster = Callable[[str, dict], dict]


class GHLTokenProvider:
    """Turns a refresh_token into a cached, auto-refreshing access_token."""

    def __init__(self, config: Optional[dict] = None, *,
                 db_path: str = memory.DB_PATH,
                 offline: bool = False,
                 token_poster: Optional[TokenPoster] = None,
                 timeout: float = 30.0) -> None:
        self.config = config if config is not None else load_oauth_config()
        self.db_path = db_path
        self.offline = offline
        self.timeout = timeout
        self._token_poster = token_poster or self._post_token_http
        self._access_token: str = ""
        self._expiry_ts: float = 0.0
        self._load_cache()

    # -- cache (memory + sqlite) -------------------------------------------
    def _load_cache(self) -> None:
        try:
            cached = memory.recall(_TOKEN_CACHE_KEY, default=None, path=self.db_path)
        except Exception:  # db not yet initialised — treat as empty cache
            cached = None
        if isinstance(cached, dict):
            self._access_token = cached.get("access_token", "") or ""
            self._expiry_ts = float(cached.get("expiry_ts", 0) or 0)

    def _store_token(self, access_token: str, expires_in: int) -> None:
        self._access_token = access_token
        self._expiry_ts = time.time() + max(int(expires_in), 0)
        try:
            memory.remember(_TOKEN_CACHE_KEY,
                            {"access_token": access_token, "expiry_ts": self._expiry_ts},
                            source="ghl-oauth", path=self.db_path)
        except Exception as exc:  # persistence is best-effort; never crash
            logger.warning("GHL OAuth: could not persist token cache: %s", exc)

    def _store_refresh_token(self, refresh_token: str) -> None:
        # GHL rotates refresh tokens; persist + prefer the newest.
        if not refresh_token or refresh_token == self.config.get("refresh_token"):
            return
        self.config["refresh_token"] = refresh_token
        try:
            memory.remember(_REFRESH_CACHE_KEY, {"refresh_token": refresh_token},
                            source="ghl-oauth", path=self.db_path)
        except Exception as exc:
            logger.warning("GHL OAuth: could not persist rotated refresh token: %s", exc)

    def _current_refresh_token(self) -> str:
        try:
            cached = memory.recall(_REFRESH_CACHE_KEY, default=None, path=self.db_path)
        except Exception:
            cached = None
        if isinstance(cached, dict) and cached.get("refresh_token"):
            return cached["refresh_token"]
        return self.config.get("refresh_token", "")

    # -- public API ---------------------------------------------------------
    def _seconds_left(self) -> float:
        return self._expiry_ts - time.time()

    def get_access_token(self, *, force: bool = False) -> str:
        """Return a valid access token, refreshing preemptively when near expiry."""
        if (not force and self._access_token
                and self._seconds_left() > PREEMPTIVE_REFRESH_SECONDS):
            return self._access_token
        return self._refresh()

    def force_refresh(self) -> str:
        """Force one refresh regardless of cache state."""
        return self._refresh()

    # -- refresh ------------------------------------------------------------
    def _refresh(self) -> str:
        if self.offline:
            self._store_token("offline-mock-access-token", 3600)
            logger.debug("GHL OAuth: offline mode — issued mock access token")
            return self._access_token

        refresh_token = self._current_refresh_token()
        if not refresh_token:
            raise GHLOAuthError("no GHL refresh_token configured (ghl.oauth.refresh_token)")

        fields = {
            "grant_type": "refresh_token",
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
            "refresh_token": refresh_token,
            "user_type": "Location",
        }
        try:
            data = self._token_poster(OAUTH_TOKEN_URL, fields)
        except Exception as exc:
            logger.warning("GHL OAuth: token refresh request failed: %s", exc)
            raise GHLOAuthError(f"GHL token refresh failed: {exc}") from exc

        access_token = (data or {}).get("access_token")
        if not access_token:
            logger.warning("GHL OAuth: refresh response missing access_token: %s", data)
            raise GHLOAuthError(f"GHL token refresh returned no access_token: {data}")

        expires_in = int((data or {}).get("expires_in", 3600) or 3600)
        self._store_token(access_token, expires_in)
        self._store_refresh_token((data or {}).get("refresh_token", ""))
        logger.info("GHL OAuth: refreshed access token (expires in %ss)", expires_in)
        return self._access_token

    # -- transport ----------------------------------------------------------
    def _post_token_http(self, url: str, fields: dict) -> dict:
        """POST the token request form-encoded. httpx if present, else urllib."""
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, data=fields,
                                   headers={"Accept": "application/json"})
                return self._parse_token_response(resp.status_code, resp.text)
        except ImportError:
            return self._post_token_urllib(url, fields)

    def _post_token_urllib(self, url: str, fields: dict) -> dict:
        import urllib.error
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return self._parse_token_response(resp.status, resp.read().decode())
        except urllib.error.HTTPError as exc:
            return self._parse_token_response(exc.code, exc.read().decode())

    @staticmethod
    def _parse_token_response(status: int, text: str) -> dict:
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {}
        if not (200 <= status < 300):
            raise GHLOAuthError(f"token endpoint returned HTTP {status}: {text[:300]}")
        return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_token_provider(*, db_path: str = memory.DB_PATH,
                         offline: Optional[bool] = None,
                         config: Optional[dict] = None
                         ) -> Optional[GHLTokenProvider]:
    """Return a token provider, or ``None`` when OAuth is not configured.

    ``None`` signals the caller to fall back to the static ``GHL_ACCESS_TOKEN``.
    """
    cfg = config if config is not None else load_oauth_config()
    off = offline if offline is not None else (os.environ.get("EVA_GHL_OFFLINE") == "1")
    if not off and not has_oauth_config(cfg):
        return None
    return GHLTokenProvider(cfg, db_path=db_path, offline=bool(off))


__all__ = [
    "GHLTokenProvider",
    "GHLOAuthError",
    "load_oauth_config",
    "has_oauth_config",
    "build_token_provider",
    "OAUTH_TOKEN_URL",
    "PREEMPTIVE_REFRESH_SECONDS",
    "DEFAULT_LOCATION_ID",
]
