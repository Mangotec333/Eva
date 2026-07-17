"""
EVA Health Monitor — monitored-module registry.

The default list is derived from the authoritative service registry in
``modules/launcher/eva_launcher.py`` (the SERVICES dict, which already carries an
explicit ``/health`` URL per module) plus the standalone modules that expose a
``/health`` route on their own default port (outreach, postcards, projects,
linkedin-analytics, monetizing-agent, ghl-agent, media-editor, eva-state,
pathfinder). Ports were confirmed by scanning each module's ``main.py``.

Override at runtime with a JSON file (``EVA_HEALTH_MONITOR_CONFIG`` -> a list of
``{"name", "url"}`` objects) so the list can evolve without a code change — the
same "edit one document to steer many agents" idea as the Agent Intelligence
Layer's current-goals artifact.
"""

from __future__ import annotations

import json
import os
from typing import Optional

_LOCALHOST = "http://localhost"


def _url(port: int) -> str:
    return f"{_LOCALHOST}:{port}/health"


# name -> port. Kept as a plain dict to match repo convention (no enums).
DEFAULT_MODULE_PORTS: dict[str, int] = {
    # --- from launcher SERVICES registry (explicit health URLs) ---
    "context-api": 8765,        # modules/logger/eva_context_api.py
    "deal-scout": 8766,
    "content-engine": 8767,
    "channels": 8770,           # channels_api.py serves 8770 (per launcher)
    "knowledge": 8771,
    "voice": 8774,
    "triage-brain": 8784,       # "diracatron"
    "finance-tracker": 8786,    # "treasurer"
    "social-scheduler": 8787,
    "deployer": 8789,
    "local-exec": 8790,
    "ip-scout": 8791,
    "brand-builder": 8792,
    # --- standalone modules with a /health route + own default port ---
    "outreach": 8768,
    "eva-state": 8769,
    "monetizing-agent": 8772,
    "pathfinder": 8773,
    "postcards": 8778,
    "projects": 8779,
    "linkedin-analytics": 8780,
    "ghl-agent": 8782,
    "media-editor": 8783,
}

# This module's own port (avoids collisions with the ports above).
HEALTH_MONITOR_PORT = 8788

# How many consecutive DOWN checks before an alert is raised.
DEFAULT_FAILURE_THRESHOLD = int(os.environ.get("EVA_HEALTH_FAILURE_THRESHOLD", "3"))

# Per-check HTTP timeout (seconds). Short so a slow module does not stall a tick.
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("EVA_HEALTH_TIMEOUT", "3"))


def default_targets() -> list[dict]:
    """The built-in monitored-module list as ``[{"name", "url"}, ...]``."""
    return [{"name": name, "url": _url(port)} for name, port in DEFAULT_MODULE_PORTS.items()]


def load_targets(config_path: Optional[str] = None) -> list[dict]:
    """Load the monitored-module list.

    Order of precedence:
      1. explicit ``config_path`` argument,
      2. ``EVA_HEALTH_MONITOR_CONFIG`` env var (path to a JSON list),
      3. the built-in ``default_targets()``.

    A config file is a JSON array of ``{"name": str, "url": str}`` objects.
    Malformed / missing files fall back to the defaults (never crash on config).
    """
    path = config_path or os.environ.get("EVA_HEALTH_MONITOR_CONFIG", "")
    if not path:
        return default_targets()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default_targets()
    targets = []
    for item in data if isinstance(data, list) else []:
        name = item.get("name")
        url = item.get("url")
        if name and url:
            targets.append({"name": name, "url": url})
    return targets or default_targets()
