"""Baseline offline tests for autostart watchdog + wake daemon pure logic."""

import importlib.util
import os
import tempfile
from pathlib import Path

# Both modules build log paths under ~/Eva/logs at import time. Point HOME at a
# temp dir so importing them never touches the real home directory.
os.environ["HOME"] = tempfile.mkdtemp()

_HERE = Path(__file__).resolve().parent


def _load(mod_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(mod_name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watchdog = _load("eva_screenpipe_watchdog", "eva-screenpipe-watchdog.py")
wake = _load("eva_wake_daemon", "eva-wake-daemon.py")


def test_should_run_pauses_when_idle():
    run, reason = watchdog.should_run_screenpipe("Cursor", watchdog.IDLE_THRESHOLD + 1)
    assert run is False
    assert "idle" in reason


def test_should_run_pauses_on_pause_app():
    run, reason = watchdog.should_run_screenpipe("Netflix", 0)
    assert run is False
    assert "pause app" in reason


def test_should_run_true_on_work_app():
    run, reason = watchdog.should_run_screenpipe("Cursor", 0)
    assert run is True
    assert "work app" in reason


def test_wake_state_touch_and_idle():
    st = wake.WakeState()
    st.active = False
    st.touch()
    assert st.active is True
    assert st.idle_seconds() >= 0.0


def test_wake_state_save_writes_json():
    st = wake.WakeState()
    st.save()  # writes under tmp HOME; must not raise
    assert wake.STATE_PATH.exists()
