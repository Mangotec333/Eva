"""
EVA Media Editor — state-ledger emitter (behind a Protocol)
===========================================================

Job lifecycle events (queued/running/done/failed/interrupted) are appended to
the governed Eva State Ledger (``modules/eva-state``, port 8769) so the whole
system shares one timeline. This mirrors modules/ghl-agent/state_client.py: the
write is behind a ``StateLedgerClient`` Protocol so tests and the sandbox never
touch the network, and any failure is an honest ``{"ok": False}`` rather than a
faked success — the edit loop still succeeds locally even if the ledger is down.

Set ``EVA_MEDIA_OFFLINE=1`` to force the stub emitter.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

STATE_LEDGER_URL = os.environ.get("EVA_STATE_URL", "http://localhost:8769")
PROJECT = "Eva Acquisition"
SOURCE_SURFACE = "media-editor"


@runtime_checkable
class StateLedgerClient(Protocol):
    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict: ...


class StubStateLedgerClient:
    """Offline emitter — records events in memory, no network."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict:
        rec = {"event_type": event_type, "summary": summary,
               "entity_id": entity_id, "payload": payload or {},
               "project": PROJECT, "source_surface": SOURCE_SURFACE}
        self.events.append(rec)
        return {"ok": True, "stub": True, "event_type": event_type}


class HttpStateLedgerClient:
    """Live emitter — POSTs to the State Ledger's /events endpoint."""

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
            "track": "acquisition",
            "entity_type": "video",
            "entity_id": entity_id,
            "payload": payload or {},
        }
        url = f"{self.base_url}/events"
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=body)
                return {"ok": 200 <= resp.status_code < 300, "status": resp.status_code}
        except ImportError:
            return self._emit_urllib(url, body)
        except Exception as exc:  # network/ledger down — honest failure
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _emit_urllib(self, url: str, body: dict) -> dict:
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return {"ok": 200 <= resp.status < 300, "status": resp.status}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_state_client(offline: Optional[bool] = None) -> StateLedgerClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_MEDIA_OFFLINE") == "1"
    return StubStateLedgerClient() if use_stub else HttpStateLedgerClient()


__all__ = [
    "StateLedgerClient",
    "StubStateLedgerClient",
    "HttpStateLedgerClient",
    "build_state_client",
    "PROJECT",
    "SOURCE_SURFACE",
]
