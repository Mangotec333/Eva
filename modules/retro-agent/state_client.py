"""
EVA Retro-Agent — eva-state ledger client (emit + read, behind a Protocol).

Mirrors ``modules/activity-tracker-agent/state_client.py`` exactly (same emit
shape, same honest-failure contract, same ``read_events`` surface) — this is the
seam that lets the weekly retro read the shared timeline every other lobe writes
to, and lets Diracatron and the other lobes see the retro digest back on that
same timeline (no side channel).
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

STATE_LEDGER_URL = os.environ.get("EVA_STATE_URL", "http://localhost:8769")
PROJECT = "Eva Acquisition"
SOURCE_SURFACE = "retro-agent"
TRACK = "ops"


@runtime_checkable
class StateLedgerClient(Protocol):
    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict: ...

    def read_events(self, *, since: Optional[str] = None,
                    limit: Optional[int] = None, **filters) -> list[dict]: ...


class StubStateLedgerClient:
    """Offline client — records emitted events in memory, serves a fixed set of
    seed events for the retro. No network."""

    def __init__(self, seed_events: Optional[list[dict]] = None) -> None:
        self.events: list[dict] = []
        self._seed_events = list(seed_events or [])

    def emit(self, *, event_type: str, summary: str = "",
             entity_id: str = "", payload: Optional[dict] = None) -> dict:
        rec = {"event_type": event_type, "summary": summary,
               "entity_id": entity_id, "payload": payload or {},
               "project": PROJECT, "source_surface": SOURCE_SURFACE,
               "track": TRACK}
        self.events.append(rec)
        return {"ok": True, "stub": True, "event_type": event_type}

    def read_events(self, *, since: Optional[str] = None,
                    limit: Optional[int] = None, **filters) -> list[dict]:
        out = list(self._seed_events) + list(self.events)
        if limit:
            out = out[:limit]
        return out


class HttpStateLedgerClient:
    """Live client — POSTs to /events, GETs /events for the weekly retro."""

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
            "entity_type": "weekly_retro",
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

    def read_events(self, *, since: Optional[str] = None,
                    limit: Optional[int] = None, **filters) -> list[dict]:
        import urllib.error
        import urllib.parse
        import urllib.request
        params = {k: v for k, v in filters.items() if v is not None}
        if since:
            params["since"] = since
        if limit:
            params["limit"] = limit
        url = f"{self.base_url}/events"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
            if isinstance(data, dict):
                data = data.get("events", [])
            return [e for e in data if isinstance(e, dict)]
        except Exception:  # ledger down — retro just reports a gap
            return []


def build_state_client(offline: Optional[bool] = None,
                       seed_events: Optional[list[dict]] = None) -> StateLedgerClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_RETRO_OFFLINE") == "1"
    if use_stub:
        return StubStateLedgerClient(seed_events=seed_events)
    return HttpStateLedgerClient()


__all__ = [
    "StateLedgerClient", "StubStateLedgerClient", "HttpStateLedgerClient",
    "build_state_client", "PROJECT", "SOURCE_SURFACE", "TRACK",
]
