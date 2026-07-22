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
