"""Pytest bootstrap: put the module dir on sys.path and force offline stub mode.

The module runs "flat" (cwd = this dir) in production; tests may be invoked from
the repo root. This makes ``import database`` / ``import service`` resolve. It
also forces the offline StubShopifyClient so no test can ever touch the network.
"""

import os
import sys

# Force the offline stub client regardless of any ambient config/credentials.
os.environ["EVA_SHOPIFY_CLIENT"] = "stub"

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
