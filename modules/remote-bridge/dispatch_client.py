"""
EVA Remote-Bridge — dispatch client (behind a Protocol).

The bridge NEVER runs anything itself. It forwards a founder's natural-language
goal to Diracatron's dispatch brain (``modules/triage-brain``, port 8784) at
``POST /triage/dispatch``, which is already registry-scoped — it can only invoke
agents Eva has explicitly registered, never raw shell / local-exec. That single
indirection is the safety boundary: the tunnel-exposed bridge can request a
*goal*, but only Diracatron decides which registered lobes act on it.

Behind a ``DispatchClient`` Protocol so tests and the sandbox run fully offline:
``StubDispatchClient`` returns a canned result (and can be told to raise, to
prove a failed dispatch is captured — not crashed), while ``HttpDispatchClient``
POSTs to the live Diracatron. Honest failure contract: a live error returns
``{"ok": false, "error": ...}`` rather than faking success.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol, runtime_checkable

DIRACATRON_URL = os.environ.get("EVA_DIRACATRON_URL", "http://localhost:8784")


@runtime_checkable
class DispatchClient(Protocol):
    def dispatch(self, *, goal: str, context: Optional[dict] = None) -> dict: ...


class StubDispatchClient:
    """Offline dispatcher — returns a canned result, never touches the network.

    Set ``raise_exc`` to an exception instance to simulate a downstream failure
    (used by tests to prove the bridge captures a failed dispatch instead of
    crashing the background task).
    """

    def __init__(self, result: Optional[dict] = None,
                 raise_exc: Optional[BaseException] = None) -> None:
        self.result = result if result is not None else {
            "ok": True, "planner": "stub", "steps": [], "results": []}
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def dispatch(self, *, goal: str, context: Optional[dict] = None) -> dict:
        self.calls.append({"goal": goal, "context": context or {}})
        if self.raise_exc is not None:
            raise self.raise_exc
        return dict(self.result)


class HttpDispatchClient:
    """Live dispatcher — POSTs the goal to Diracatron's /triage/dispatch."""

    def __init__(self, base_url: str = DIRACATRON_URL, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def dispatch(self, *, goal: str, context: Optional[dict] = None) -> dict:
        body = {"goal": goal, "context": context or {}}
        url = f"{self.base_url}/triage/dispatch"
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                parsed = json.loads(raw) if raw else {}
                parsed.setdefault("ok", 200 <= resp.status < 300)
                return parsed
        except Exception as exc:  # Diracatron down / bad response — honest failure
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_dispatch_client(offline: Optional[bool] = None) -> DispatchClient:
    use_stub = offline
    if use_stub is None:
        use_stub = os.environ.get("EVA_REMOTE_BRIDGE_OFFLINE") == "1"
    return StubDispatchClient() if use_stub else HttpDispatchClient()


__all__ = [
    "DispatchClient",
    "StubDispatchClient",
    "HttpDispatchClient",
    "build_dispatch_client",
    "DIRACATRON_URL",
]
