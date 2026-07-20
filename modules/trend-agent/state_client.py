"""
EVA Trend-Agent — eva-state ledger client (emit-only, behind a Protocol).
Mirrors ``modules/idea-generator-agent/state_client.py`` exactly (same emit
shape, same honest-failure contract). This is the seam that makes Diracatron
and every other lobe see a completed/refuted thesis run on the shared
timeline — no separate sync mechanism needed.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

STATE_LEDGER_URL = os.environ.get("EVA_STATE_URL", "http://localhost:8769")
PROJECT = "Eva Acquisition"
SOURCE_SURFACE = "trend-agent"
TRACK = "strategy"


@runtime_checkable
class StateLedgerClient(Protocol):
    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict: ...


class StubStateLedgerClient:
    """Offline client — records emitted events in memory. No network."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict:
        rec = {"event_type": event_type, "summary": summary,
               "entity_id": entity_id, "payload": payload or {},
               "project": PROJECT, "source_surface": SOURCE_SURFACE,
               "track": TRACK}
        self.events.append(rec)
        return {"ok": True, "stub": True, "event_type": event_type}


class HttpStateLedgerClient:
    """Live client — POSTs to /events. Ledger down is an honest failure, never
    raised — a stress-test run still returns its result either way."""

    def __init__(self, base_url: str = STATE_LEDGER_URL, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict:
        body = {
            "event_type": event_type,
            "summary": summary,
            "actor": "Eva",
            "source_surface": SOURCE_SURFACE,
            "project": PROJECT,
            "track": TRACK,
            "entity_type": "thesis_run",
            "entity_id": entity_id,
            "payload": payload or {},
        }
        import urllib.error
        import urllib.request
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.base_url}/events", data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return {"ok": 200 <= resp.status < 300, "status": resp.status}
        except Exception as exc:  # network/ledger down — honest failure
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_state_client(offline: Optional[bool] = None) -> StateLedgerClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_TREND_OFFLINE") == "1"
    if use_stub:
        return StubStateLedgerClient()
    return HttpStateLedgerClient()


__all__ = [
    "StateLedgerClient", "StubStateLedgerClient", "HttpStateLedgerClient",
    "build_state_client", "PROJECT", "SOURCE_SURFACE", "TRACK",
]
