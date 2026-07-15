"""
EVA Social-Publish — credential detection for LinkedIn + X (Twitter).

Reuses the same source the channels connectors read from:
``~/.eva/channels_config.json`` (see modules/channels), with an env-var
fallback so nothing has to be hardcoded. Produces a connector-compatible
``cfg`` dict ({"linkedin": {...}, "twitter": {...}}) and a human-readable
report of exactly what's missing and where to set it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CHANNELS_CONFIG_PATH = Path.home() / ".eva" / "channels_config.json"

# Env fallbacks (set these in ~/.zshrc on the Mac, or the launchd plist).
LINKEDIN_ENV = {
    "access_token": "LINKEDIN_ACCESS_TOKEN",
    "person_urn": "LINKEDIN_PERSON_URN",
}
# X/Twitter uses OAuth 1.0a user context (tweepy) — 4 values.
X_ENV = {
    "api_key": "X_API_KEY",
    "api_secret": "X_API_SECRET",
    "access_token": "X_ACCESS_TOKEN",
    "access_secret": "X_ACCESS_SECRET",
}
# Legacy TWITTER_* env names are also accepted.
X_ENV_LEGACY = {
    "api_key": "TWITTER_API_KEY",
    "api_secret": "TWITTER_API_SECRET",
    "access_token": "TWITTER_ACCESS_TOKEN",
    "access_secret": "TWITTER_ACCESS_SECRET",
}


def _load_channels_config() -> dict:
    try:
        with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, ValueError):
        return {}


def _resolve(section: dict, env_map: dict, legacy_map: dict | None = None) -> dict:
    """For each field prefer the config-file value, then env, then legacy env."""
    out = {}
    for field, env_name in env_map.items():
        val = (section.get(field) or "").strip() if isinstance(section.get(field), str) else section.get(field)
        if not val:
            val = os.environ.get(env_name, "").strip()
        if not val and legacy_map:
            val = os.environ.get(legacy_map[field], "").strip()
        out[field] = val or ""
    return out


def build_cfg() -> dict:
    """Return a cfg dict shaped for the channels connectors."""
    cfg_file = _load_channels_config()
    linkedin = _resolve(cfg_file.get("linkedin", {}) or {}, LINKEDIN_ENV)
    twitter = _resolve(cfg_file.get("twitter", {}) or {}, X_ENV, X_ENV_LEGACY)
    return {"linkedin": linkedin, "twitter": twitter}


def detect() -> dict:
    """Report configured/missing state per platform with setup hints."""
    cfg = build_cfg()

    li = cfg["linkedin"]
    li_missing = [LINKEDIN_ENV[f] for f in ("access_token", "person_urn") if not li.get(f)]
    linkedin_report = {
        "configured": not li_missing,
        "missing_env": li_missing,
        "required": list(LINKEDIN_ENV.values()),
    }

    tw = cfg["twitter"]
    tw_missing = [X_ENV[f] for f in ("api_key", "api_secret", "access_token", "access_secret")
                  if not tw.get(f)]
    x_report = {
        "configured": not tw_missing,
        "missing_env": tw_missing,
        "required": list(X_ENV.values()),
    }

    return {
        "config_file": str(CHANNELS_CONFIG_PATH),
        "config_file_exists": CHANNELS_CONFIG_PATH.exists(),
        "linkedin": linkedin_report,
        "x": x_report,
        "all_configured": linkedin_report["configured"] and x_report["configured"],
        "setup_hint": (
            "Set credentials in ~/.eva/channels_config.json (linkedin.access_token, "
            "linkedin.person_urn, twitter.api_key/api_secret/access_token/access_secret) "
            "OR export the env vars in ~/.zshrc: "
            f"{', '.join(list(LINKEDIN_ENV.values()) + list(X_ENV.values()))}. "
            "launchd services do not source ~/.zshrc — put env vars in the plist "
            "EnvironmentVariables or restart from an interactive shell."
        ),
    }
