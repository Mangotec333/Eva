"""
Minimal pytest shim
====================
The sandbox has no pytest installed, but the launcher test suite is written
pytest-native. This shim provides just enough of the pytest surface the suite
uses (``raises``, ``fixture``, ``mark``) plus a stdlib runner so the tests run
anywhere the module runs:

    python test_autonomy.py

Tests import it via a try/except fallback:

    try:
        import pytest
    except ImportError:
        import _pytest_shim as pytest
"""

from __future__ import annotations

import sys
from contextlib import contextmanager


class _RaisesContext:
    def __init__(self, expected):
        self.expected = expected
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(
                f"DID NOT RAISE {getattr(self.expected, '__name__', self.expected)}"
            )
        if not issubclass(exc_type, self.expected):
            return False  # let the unexpected exception propagate
        self.value = exc
        return True


def raises(expected):
    return _RaisesContext(expected)


def fixture(func=None, **_kwargs):
    """No-op fixture marker. Tests here don't rely on fixture injection."""
    if func is None:
        def _decorator(f):
            return f
        return _decorator
    return func


class _Mark:
    def __getattr__(self, _name):
        def _decorator(func=None, **_kw):
            if func is None:
                return lambda f: f
            return func
        return _decorator


mark = _Mark()


def main(_argv=None):
    """Run every top-level test_* callable in the caller's __main__ module."""
    module = sys.modules["__main__"]
    tests = [
        (name, obj)
        for name, obj in sorted(vars(module).items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {name}")
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return 1 if failed else 0
