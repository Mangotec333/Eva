"""
Autonomy graduation tracker — offline test suite (zero network).

pytest-native, with a stdlib fallback shim so it runs without pytest installed:

    cd modules/launcher && python3 test_autonomy.py
    (or, if pytest is available)  python3 -m pytest test_autonomy.py

Nothing here EVER touches the real ~/.eva: HOME is redirected to a temp dir
*before* the launcher is imported (so the module-level seed writes into the
sandbox), and every tracker under test is pointed at its own temp store/history.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# Redirect HOME to a throwaway dir BEFORE importing the launcher, so its
# import-time seed() (and any AutonomyTracker default paths) can never write to
# the real ~/.eva.
_FAKE_HOME = tempfile.mkdtemp(prefix="eva_autonomy_home_")
os.environ["HOME"] = _FAKE_HOME

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pytest
except ImportError:  # sandbox has no pytest — use the local shim
    import _pytest_shim as pytest

from fastapi.testclient import TestClient

import autonomy as autonomy_mod
from autonomy import (
    STATUS_AUTONOMOUS,
    STATUS_MANUAL,
    AutonomyTracker,
)

FIXED_NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
FIXED_CLOCK = lambda: FIXED_NOW  # noqa: E731

# A tiny fake SERVICES map. "with_dir" resolves to a modules/ path (git-derived),
# "no_dir" mimics the external screenpipe binary (no module dir → shipped None).
FAKE_SERVICES = {
    "with_dir": {"cmd": "cd /x/modules/logger && python3 eva_logger.py", "port": 1},
    "no_dir": {"cmd": "screenpipe", "port": 2},
}


def _tmp_tracker(services=None, *, repo_root=None, clock=FIXED_CLOCK):
    d = tempfile.mkdtemp(prefix="eva_autonomy_test_")
    return AutonomyTracker(
        services if services is not None else FAKE_SERVICES,
        store_path=os.path.join(d, "autonomy_status.json"),
        history_path=os.path.join(d, "autonomy_history.jsonl"),
        repo_root=repo_root or d,  # non-git temp dir → shipped_at falls back to None
        clock=clock,
    )


def _iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------

def test_seed_creates_a_record_per_service():
    t = _tmp_tracker()
    result = t.seed()
    assert set(result["seeded"]) == {"with_dir", "no_dir"}
    records = {r["module"]: r for r in t.list_all()}
    assert records["with_dir"]["status"] == STATUS_MANUAL
    assert records["with_dir"]["graduated_at"] is None
    # non-git temp repo_root → shipped_at falls back to None (never crashes)
    assert records["no_dir"]["shipped_at"] is None


def test_seed_is_idempotent_and_never_resets():
    t = _tmp_tracker()
    t.seed()
    # Human graduates one module...
    t.graduate("with_dir")
    assert t.status_of("with_dir") == STATUS_AUTONOMOUS
    # ...re-seeding must NOT duplicate keys or reset the graduated status.
    second = t.seed()
    assert second["seeded"] == []            # nothing new added
    assert second["total"] == 2              # still exactly two
    assert t.status_of("with_dir") == STATUS_AUTONOMOUS  # not reset


def test_seed_never_crashes_without_git():
    # repo_root points at a plain temp dir (no .git) → derivation returns None.
    t = _tmp_tracker(services={"m": {"cmd": "cd /x/modules/knowledge && python3 x.py"}})
    t.seed()  # must not raise
    rec = t.get("m")
    assert rec["shipped_at"] is None
    assert rec["graduation_eligible"] is False
    assert rec["days_since_shipped"] is None


# ---------------------------------------------------------------------------
# eligibility (fixed clock)
# ---------------------------------------------------------------------------

def _seed_with_shipped(tracker, module, shipped_dt, status=STATUS_MANUAL):
    """Write a record directly so we control shipped_at precisely."""
    records = tracker._load()
    records[module] = {
        "module": module,
        "status": status,
        "shipped_at": _iso(shipped_dt),
        "graduated_at": None,
    }
    tracker._save(records)


def test_module_shipped_20_days_ago_is_eligible():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "old", FIXED_NOW - timedelta(days=20))
    rec = t.get("old")
    assert rec["days_since_shipped"] == 20
    assert rec["days_until_eligible"] == 0
    assert rec["graduation_eligible"] is True


def test_module_shipped_3_days_ago_is_not_eligible():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "young", FIXED_NOW - timedelta(days=3))
    rec = t.get("young")
    assert rec["days_since_shipped"] == 3
    assert rec["days_until_eligible"] == 11  # 14 - 3
    assert rec["graduation_eligible"] is False


def test_exactly_14_days_is_eligible():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "edge", FIXED_NOW - timedelta(days=14))
    assert t.get("edge")["graduation_eligible"] is True


# ---------------------------------------------------------------------------
# graduate / revert transitions + history
# ---------------------------------------------------------------------------

def test_graduate_flips_status_sets_graduated_at_and_appends_history():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "m", FIXED_NOW - timedelta(days=20))
    assert t.get("m")["graduation_eligible"] is True  # eligible before

    rec = t.graduate("m")
    assert rec["status"] == STATUS_AUTONOMOUS
    assert rec["graduated_at"] == _iso(FIXED_NOW)
    # Already autonomous → no longer "eligible" (eligibility is a manual-only state).
    assert rec["graduation_eligible"] is False

    hist = t.history("m")
    assert len(hist) == 1
    assert hist[0]["from_status"] == STATUS_MANUAL
    assert hist[0]["to_status"] == STATUS_AUTONOMOUS
    assert hist[0]["action"] == "graduate"


def test_revert_flips_back_and_appends_history():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "m", FIXED_NOW - timedelta(days=20))
    t.graduate("m")
    rec = t.revert("m")
    assert rec["status"] == STATUS_MANUAL
    assert rec["graduated_at"] is None
    assert rec["graduation_eligible"] is True  # manual + old again

    hist = t.history("m")  # newest first
    assert len(hist) == 2
    assert hist[0]["action"] == "revert"
    assert hist[1]["action"] == "graduate"


def test_graduate_unknown_module_returns_none():
    t = _tmp_tracker(services={})
    assert t.graduate("nope") is None
    assert t.revert("nope") is None
    assert t.get("nope") is None


def test_history_is_append_only_across_transitions():
    t = _tmp_tracker(services={})
    _seed_with_shipped(t, "m", FIXED_NOW - timedelta(days=20))
    t.graduate("m")
    t.revert("m")
    t.graduate("m")
    hist = t.history("m")
    assert [h["action"] for h in hist] == ["graduate", "revert", "graduate"]


# ---------------------------------------------------------------------------
# config-file-primary round-trip
# ---------------------------------------------------------------------------

def test_store_round_trips_to_disk_json():
    d = tempfile.mkdtemp(prefix="eva_autonomy_rt_")
    store = os.path.join(d, "autonomy_status.json")
    t1 = AutonomyTracker(
        {"a": {"cmd": "cd /x/modules/voice && python3 v.py"}},
        store_path=store, history_path=os.path.join(d, "h.jsonl"),
        repo_root=d, clock=FIXED_CLOCK,
    )
    t1.seed()
    t1.graduate("a")

    # On-disk JSON is real and readable.
    on_disk = json.loads(open(store).read())
    assert on_disk["a"]["status"] == STATUS_AUTONOMOUS

    # A fresh tracker over the same file sees the persisted state.
    t2 = AutonomyTracker(
        {"a": {"cmd": "cd /x/modules/voice && python3 v.py"}},
        store_path=store, history_path=os.path.join(d, "h.jsonl"),
        repo_root=d, clock=FIXED_CLOCK,
    )
    assert t2.status_of("a") == STATUS_AUTONOMOUS


def test_missing_store_file_falls_back_to_empty():
    d = tempfile.mkdtemp(prefix="eva_autonomy_missing_")
    t = AutonomyTracker(
        {}, store_path=os.path.join(d, "does_not_exist.json"),
        history_path=os.path.join(d, "h.jsonl"), repo_root=d, clock=FIXED_CLOCK,
    )
    assert t.list_all() == []
    assert t.get("x") is None


# ---------------------------------------------------------------------------
# launcher HTTP surface (TestClient) — routes + /status field, unknown → 404
# ---------------------------------------------------------------------------

def _client_with_temp_tracker():
    """A TestClient whose launcher tracker is redirected to temp storage."""
    import eva_launcher as launcher
    d = tempfile.mkdtemp(prefix="eva_autonomy_http_")
    launcher.autonomy = AutonomyTracker(
        launcher.SERVICES,
        store_path=os.path.join(d, "autonomy_status.json"),
        history_path=os.path.join(d, "autonomy_history.jsonl"),
        repo_root=launcher.autonomy.repo_root,  # real repo → real shipped dates
        clock=FIXED_CLOCK,
    )
    launcher.autonomy.seed()
    return TestClient(launcher.app), launcher


def test_status_route_includes_autonomy_status_without_breaking_fields():
    client, launcher = _client_with_temp_tracker()
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    # New field present, one entry per service, valid values.
    assert "autonomy_status" in body
    assert set(body["autonomy_status"]) == set(launcher.SERVICES)
    for val in body["autonomy_status"].values():
        assert val in (STATUS_MANUAL, STATUS_AUTONOMOUS)
    # Existing fields untouched.
    for key in ("services", "details", "online", "online_count", "total",
                "all_online", "timestamp"):
        assert key in body


def test_autonomy_list_and_get_routes():
    client, launcher = _client_with_temp_tracker()
    lst = client.get("/autonomy").json()["modules"]
    assert len(lst) == len(launcher.SERVICES)
    sample = next(iter(launcher.SERVICES))
    rec = client.get(f"/autonomy/{sample}").json()
    assert rec["module"] == sample
    assert "graduation_eligible" in rec
    assert "days_since_shipped" in rec
    assert "days_until_eligible" in rec


def test_graduate_and_revert_routes_and_history():
    client, launcher = _client_with_temp_tracker()
    sample = next(iter(launcher.SERVICES))

    grad = client.post(f"/autonomy/{sample}/graduate").json()
    assert grad["status"] == STATUS_AUTONOMOUS
    assert grad["graduated_at"] is not None

    # /status now reflects it
    st = client.get("/status").json()
    assert st["autonomy_status"][sample] == STATUS_AUTONOMOUS

    rev = client.post(f"/autonomy/{sample}/revert").json()
    assert rev["status"] == STATUS_MANUAL
    assert rev["graduated_at"] is None

    hist = client.get(f"/autonomy/{sample}/history").json()["history"]
    assert [h["action"] for h in hist] == ["revert", "graduate"]


def test_unknown_module_returns_404_on_all_routes():
    client, _ = _client_with_temp_tracker()
    assert client.get("/autonomy/nope").status_code == 404
    assert client.post("/autonomy/nope/graduate").status_code == 404
    assert client.post("/autonomy/nope/revert").status_code == 404
    assert client.get("/autonomy/nope/history").status_code == 404


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
