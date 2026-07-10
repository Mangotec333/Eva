"""Pytest bootstrap: put the module dir and modules/ root on sys.path.

The module runs "flat" (cwd = this dir) in production; tests are invoked from the
repo root. This makes both ``import memory`` (module-local) and shared sibling
imports under ``modules/`` (e.g. ``voice_dna``) resolve. Also forces offline mode
so no test can touch the network.
"""

import os
import sys

os.environ.setdefault("EVA_GHL_OFFLINE", "1")

_HERE = os.path.dirname(__file__)
_MODULES = os.path.abspath(os.path.join(_HERE, ".."))
_CONTENT = os.path.join(_MODULES, "content-engine")

for p in (_HERE, _MODULES, _CONTENT):
    if p not in sys.path:
        sys.path.insert(0, p)
