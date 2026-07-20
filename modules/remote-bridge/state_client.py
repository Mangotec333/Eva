"""
EVA Remote-Bridge — state-ledger emitter (behind a Protocol).

Every remote instruction lifecycle transition the bridge performs —
``received`` → ``dispatched`` → ``complete`` / ``failed``, plus the security
events ``unauthorized`` and ``rate_limited`` — is written back to the governed
Eva State Ledger (``modules/eva-state``, port 8769) so the whole system shares
one timeline and Eva can audit exactly what the founder asked for and when.

This module is the single seam for that write, behind a ``StateLedgerClient``
Protocol so tests and the sandbox never touch the network. An audit write must
NEVER block or fail the HTTP response — the live client returns an honest
``{"ok": false}`` on any error rather than raising.

Mirrors ``modules/local-exec/state_client.py`` and
``modules/triage-brain/state_client.py`` (same shape, same honest-failure
contract) — only ``SOURCE_SURFACE`` / ``entity_type`` differ.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

STATE_LEDGER_URL = os.environ.get("EVA_STATE_URL", "http://localhost:8769")
PROJECT = "Eva Acquisition"
SOURCE_SURFACE = "remote-bridge"


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
            "track": "infra",
            "entity_type": "remote_instruction",
            "entity_id": entity_id,
            "payload": payload or {},
        }
        url = f"{self.base_url}/events"
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return {"ok": 200 <= resp.status < 300, "status": resp.status}
        except Exception as exc:  # network/ledger down — honest failure, never raise
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_state_client(offline: Optional[bool] = None) -> StateLedgerClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_REMOTE_BRIDGE_OFFLINE") == "1"
    return StubStateLedgerClient() if use_stub else HttpStateLedgerClient()


__all__ = [
    "StateLedgerClient",
    "StubStateLedgerClient",
    "HttpStateLedgerClient",
    "build_state_client",
    "PROJECT",
    "SOURCE_SURFACE",
]
