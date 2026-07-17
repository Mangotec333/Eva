"""Baseline offline tests for lovable-bridge (health + db roundtrip, no network)."""

import importlib.util
import os
import tempfile
from pathlib import Path

# init_db() runs at import and writes under ~/Eva/logs. Point HOME at a temp dir
# so importing the module never touches the real home directory.
os.environ["HOME"] = tempfile.mkdtemp()

_spec = importlib.util.spec_from_file_location(
    "eva_lovable_bridge",
    Path(__file__).resolve().parent / "eva_lovable_bridge.py",
)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


def test_health_returns_online():
    payload = bridge.health()
    assert payload["status"] == "online"
    assert payload["service"] == "eva_lovable_bridge"


def test_save_and_get_history_roundtrip():
    build_id = bridge.db_save_build("a deal tracker idea", "full prompt text",
                                    "https://lovable.dev/?x", "deal-tracker")
    assert isinstance(build_id, int)
    history = bridge.db_get_history(limit=10)
    assert any(b["id"] == build_id and b["idea"] == "a deal tracker idea" for b in history)
