"""Pytest bootstrap: put the module dir and modules/ root on sys.path.

The module runs "flat" (cwd = this dir) in production; tests are invoked from
the repo root. This makes both ``import memory`` (module-local) and
``import kb_index`` (the shared sibling package under modules/) resolve.
"""

import os
import sys

_HERE = os.path.dirname(__file__)
_MODULES = os.path.abspath(os.path.join(_HERE, ".."))

for p in (_HERE, _MODULES):
    if p not in sys.path:
        sys.path.insert(0, p)
