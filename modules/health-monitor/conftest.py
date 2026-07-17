"""Pytest bootstrap: put the module dir on sys.path and force offline mode.

The module runs "flat" (cwd = this dir) in production; tests are invoked from the
repo root or the module dir. This makes module-local imports (``service``,
``database``, ``config``, ``http_client``) resolve, and forces the offline stub
HealthClient so no test can touch the network.
"""

import os
import sys

# Force the offline stub probe for every test — zero outbound calls.
os.environ.setdefault("EVA_HEALTH_CLIENT", "stub")

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
