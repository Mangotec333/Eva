"""Vercel Python (ASGI) entrypoint for the EVA Deal Scout FastAPI service.

Vercel's ``@vercel/python`` runtime serves the module-level ``app`` ASGI
callable.  The service source lives one directory up, so we add it to
``sys.path`` before importing the FastAPI app.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402  (path set up above)

__all__ = ["app"]
