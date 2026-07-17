"""Pytest bootstrap: put the module dir and the EVA repo root on sys.path.

The module runs "flat" (cwd = this dir) in production; tests are invoked from the
repo root or the module dir. This makes both module-local imports (``service``,
``database``) and shared ``services.*`` libs resolve. Forces the offline stub
transports so no test can touch the network.
"""

import os
import sys

# Default to offline stub transports for every test.
os.environ.setdefault("EVA_MEET_DRIVE", "stub")
os.environ.setdefault("EVA_MEET_TRANSCRIBER", "stub")

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

for p in (_HERE, _REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
