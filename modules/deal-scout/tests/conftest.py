"""Shared pytest fixtures — put the module dir on sys.path so the pipeline
modules import without a package install."""

import os
import sys

import pytest

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture()
def store():
    from store import SQLiteDealStore

    s = SQLiteDealStore(":memory:")
    s.migrate()
    yield s
    s.close()


@pytest.fixture()
def fixtures_dir():
    return FIXTURES
