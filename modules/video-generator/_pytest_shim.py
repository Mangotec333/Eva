"""
Minimal pytest shim — ONLY used when real pytest is unavailable (e.g. a network-
less sandbox). It implements just enough of the pytest surface the test suite
uses (``fixture``, ``raises``, ``mark.skipif``, ``fixture``-style dependency
injection by parameter name, and a ``tmp_path`` builtin fixture) to run the
suite standalone via ``python test_video_generator.py``.

On a normal machine ``import pytest`` succeeds and this file is never imported;
``python -m pytest`` uses real pytest. This shim keeps the offline suite green
where pytest cannot be pip-installed.
"""

from __future__ import annotations

import inspect
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

_FIXTURES: dict = {}


def fixture(func=None, **_kwargs):
    def register(f):
        _FIXTURES[f.__name__] = f
        f._is_fixture = True
        return f
    if func is not None and callable(func):
        return register(func)
    return register


@contextmanager
def raises(exc_type):
    raised = {}
    try:
        yield raised
    except exc_type as exc:
        raised["value"] = exc
        return
    except Exception as exc:  # wrong exception type
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(exc).__name__}: {exc}")
    raise AssertionError(f"{exc_type.__name__} was not raised")


class _Skip(Exception):
    pass


class _Mark:
    @staticmethod
    def skipif(condition, reason=""):
        def deco(f):
            if condition:
                f._skip = reason or "skipped"
            return f
        return deco


mark = _Mark()


def _resolve(name: str, cache: dict):
    if name in cache:
        return cache[name]
    if name == "tmp_path":
        val = Path(tempfile.mkdtemp())
        cache[name] = val
        return val
    if name not in _FIXTURES:
        raise KeyError(f"no fixture named {name!r}")
    factory = _FIXTURES[name]
    params = inspect.signature(factory).parameters
    kwargs = {p: _resolve(p, cache) for p in params}
    val = factory(**kwargs)
    cache[name] = val
    return val


def _run(namespace: dict) -> int:
    tests = sorted(
        (name, obj) for name, obj in namespace.items()
        if name.startswith("test_") and callable(obj)
        and not getattr(obj, "_is_fixture", False)
    )
    passed = skipped = failed = 0
    for name, fn in tests:
        if getattr(fn, "_skip", None):
            print(f"SKIP {name} ({fn._skip})")
            skipped += 1
            continue
        cache: dict = {}
        params = inspect.signature(fn).parameters
        try:
            kwargs = {p: _resolve(p, cache) for p in params}
            fn(**kwargs)
            print(f"PASS {name}")
            passed += 1
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0
