"""
EVA IP-Scout — prior-art provider credential detection (config-file-primary).

Mirrors ``modules/social-publish/credentials.py``: the PatentsView API key is
read from the shared ``~/.eva/channels_config.json`` under an ``ip_scout``
section, with an env-var fallback (``PATENTSVIEW_API_KEY``) so nothing has to be
hardcoded. The key is OPTIONAL — IP-Scout runs offline (mocked provider) without
it, so a missing key is never an error.

Config file shape:
  {
    "ip_scout": {
      "patentsview_api_key": "..."
    }
  }
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CHANNELS_CONFIG_PATH = Path.home() / ".eva" / "channels_config.json"

PATENTSVIEW_ENV = "PATENTSVIEW_API_KEY"


def _load_channels_config() -> dict:
    try:
        with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, ValueError):
        return {}


def build_cfg() -> dict:
    """Return the ip_scout provider config (config-file value → env fallback)."""
    section = _load_channels_config().get("ip_scout", {}) or {}
    key = section.get("patentsview_api_key")
    key = key.strip() if isinstance(key, str) else ""
    if not key:
        key = os.environ.get(PATENTSVIEW_ENV, "").strip()
    return {"patentsview_api_key": key or ""}


def detect() -> dict:
    """Report configured/missing state with a setup hint."""
    cfg = build_cfg()
    configured = bool(cfg.get("patentsview_api_key"))
    return {
        "config_file": str(CHANNELS_CONFIG_PATH),
        "config_file_exists": CHANNELS_CONFIG_PATH.exists(),
        "patentsview": {
            "configured": configured,
            "required_env": PATENTSVIEW_ENV,
        },
        "note": (
            "PatentsView is OPTIONAL — IP-Scout triages offline with a mocked "
            "provider when no key is present."
        ),
        "setup_hint": (
            "Set ip_scout.patentsview_api_key in ~/.eva/channels_config.json OR "
            f"export {PATENTSVIEW_ENV} in ~/.zshrc. launchd services do not "
            "source ~/.zshrc — put env vars in the plist EnvironmentVariables."
        ),
    }


__all__ = ["build_cfg", "detect", "CHANNELS_CONFIG_PATH", "PATENTSVIEW_ENV"]
