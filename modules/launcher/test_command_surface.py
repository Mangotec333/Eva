"""
EVA Launcher — offline test for GET /command-surface (zero network).

Importing ``eva_launcher`` only defines the FastAPI app; the per-module service
imports are all lazy (they happen inside route handlers, not at import time), and
``/command-surface`` introspects ``app.routes`` without calling any of them — so
this suite runs with zero network calls and no unavailable-dep imports. We do NOT
exercise ``/triage/dispatch``'s dispatch behaviour here (that is triage-brain's
own ``test_diracatron.py``).

Runs under real pytest, or standalone via the bundled shim when pytest is not
installed (a networkless sandbox):

  python test_command_surface.py
  (or)  python -m pytest modules/launcher/test_command_surface.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pytest  # noqa: F401
except ImportError:  # networkless sandbox — use the bundled shim
    import _pytest_shim as pytest  # type: ignore  # noqa: F401

from fastapi.testclient import TestClient

import eva_launcher

client = TestClient(eva_launcher.app)


def _surface() -> dict:
    r = client.get("/command-surface")
    assert r.status_code == 200
    return r.json()


def test_command_surface_returns_both_buckets_nonempty():
    body = _surface()
    assert "founder_command_entry" in body
    assert "system_internal" in body
    assert isinstance(body["founder_command_entry"], list)
    assert isinstance(body["system_internal"], list)
    assert len(body["founder_command_entry"]) > 0
    assert len(body["system_internal"]) > 0


def test_guidance_string_present_and_points_at_triage_dispatch():
    body = _surface()
    assert isinstance(body.get("guidance"), str)
    assert body["guidance"].strip()
    assert "/triage/dispatch" in body["guidance"]


def test_all_triage_routes_are_founder_and_none_are_internal():
    body = _surface()
    founder_paths = {e["path"] for e in body["founder_command_entry"]}
    internal_paths = {e["path"] for e in body["system_internal"]}

    # every founder route is a /triage route ...
    assert founder_paths, "expected at least one /triage route"
    assert all(p.startswith("/triage") for p in founder_paths)

    # ... and no /triage route leaked into system_internal
    assert not any(p.startswith("/triage") for p in internal_paths)

    # cross-check against the live app: EVERY /triage route the app registered
    # must show up under founder_command_entry (nothing dropped).
    from fastapi.routing import APIRoute
    live_triage = {
        route.path for route in eva_launcher.app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/triage")
    }
    assert live_triage == founder_paths


def test_no_duplicate_paths_anywhere():
    body = _surface()
    founder_paths = [e["path"] for e in body["founder_command_entry"]]
    internal_paths = [e["path"] for e in body["system_internal"]]
    all_paths = founder_paths + internal_paths

    # no duplicates within each bucket, none across buckets
    assert len(founder_paths) == len(set(founder_paths))
    assert len(internal_paths) == len(set(internal_paths))
    assert len(all_paths) == len(set(all_paths))


def test_entries_carry_path_and_methods():
    body = _surface()
    for entry in body["founder_command_entry"] + body["system_internal"]:
        assert entry["path"].startswith("/")
        assert isinstance(entry["methods"], list) and entry["methods"]
        # methods are real HTTP verbs, never the auto-added HEAD/OPTIONS noise
        assert all(m == m.upper() for m in entry["methods"])
        assert "HEAD" not in entry["methods"] and "OPTIONS" not in entry["methods"]


def test_known_sensitive_routes_are_system_internal():
    body = _surface()
    internal_paths = {e["path"] for e in body["system_internal"]}
    # these powerful direct-action routes must NOT be advertised as a front door
    for sensitive in ("/local-exec/exec", "/terminal/exec"):
        assert sensitive in internal_paths


if __name__ == "__main__":
    raise SystemExit(pytest._run(dict(globals())))
