"""Shared pytest fixtures.

Put the module dir on sys.path so the flat modules import without a package
install (mirrors deal-scout/tests/conftest.py). All stores are opened on
in-memory SQLite so no real financial data is ever written during tests.
"""

import os
import sys

import pytest

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# Env vars this module reads at call time. If any is exported in the developer's
# real shell it can bleed into a test — most dangerously SIMPLEFIN_BRIDGE_URL,
# which carries live basic-auth credentials and could surface in an assertion
# stack trace. Clear them all before every test so behavior is deterministic
# regardless of ambient environment; a test that needs a value sets it explicitly
# (monkeypatch.setenv runs after this autouse fixture).
_MODULE_ENV_VARS = (
    "SIMPLEFIN_BRIDGE_URL",
    "TREASURER_PROVIDER",
    "TREASURER_ACCOUNT_MAP_PATH",
    "TREASURER_CSV_PATH",
)


@pytest.fixture(autouse=True)
def _isolate_module_env(monkeypatch):
    for var in _MODULE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def fixtures_dir():
    return FIXTURES


@pytest.fixture()
def personal_store():
    from store import TreasurerStore

    s = TreasurerStore("personal", ":memory:")
    s.migrate()
    yield s
    s.close()


@pytest.fixture()
def business_store():
    from store import TreasurerStore

    s = TreasurerStore("business", ":memory:")
    s.migrate()
    yield s
    s.close()
