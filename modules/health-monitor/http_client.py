"""
EVA Health Monitor — HTTP probe transport (the single network chokepoint).

Per the Architecture Directive (rule #3) all network I/O sits behind a
``HealthClient`` Protocol with a ``StubHealthClient`` (offline, canned responses —
used in tests, no network) and a ``RealHealthClient`` (the actual probe). The real
client uses stdlib ``urllib`` so the module adds **no** new dependency to poll a
``/health`` endpoint.

Both return a ``ProbeResult``; the client never raises on a normal failure
(timeout, connection refused, non-200) — it returns ``ok=False`` with the error,
so a down module is data, not an exception.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class ProbeResult:
    ok: bool
    http_code: int = 0
    latency_ms: float = -1.0
    error: str = ""


@runtime_checkable
class HealthClient(Protocol):
    """Probe transport. Implementations must not raise on a normal failure;
    they return a ``ProbeResult`` with ``ok=False`` instead."""

    name: str

    def probe(self, url: str, timeout: float = 3.0) -> ProbeResult: ...


# ---------------------------------------------------------------------------
# Stub (offline, canned) — used in tests. No network.
# ---------------------------------------------------------------------------

class StubHealthClient:
    """Offline HealthClient driven by a canned per-URL response map.

    ``responses`` maps a URL to a ``ProbeResult`` (or a dict of its fields).
    Unknown URLs return ``default`` (a down result by default), so a test can
    make a specific module "up" and leave the rest "down" without wiring real
    sockets. Records every probed URL in ``calls`` for assertions.
    """

    name = "stub"

    def __init__(
        self,
        responses: Optional[dict] = None,
        default: Optional[ProbeResult] = None,
    ):
        self.responses = responses or {}
        self.default = default if default is not None else ProbeResult(
            ok=False, http_code=0, latency_ms=-1.0, error="stub: connection refused"
        )
        self.calls: list[str] = []

    def set(self, url: str, result) -> None:
        self.responses[url] = result

    def probe(self, url: str, timeout: float = 3.0) -> ProbeResult:
        self.calls.append(url)
        res = self.responses.get(url, self.default)
        if isinstance(res, ProbeResult):
            return res
        if isinstance(res, dict):
            return ProbeResult(
                ok=res.get("ok", False),
                http_code=res.get("http_code", 200 if res.get("ok") else 0),
                latency_ms=res.get("latency_ms", 1.0 if res.get("ok") else -1.0),
                error=res.get("error", ""),
            )
        # A bare truthy/falsey convenience value.
        return ProbeResult(ok=bool(res), http_code=200 if res else 0)


# ---------------------------------------------------------------------------
# Real (stdlib urllib) — the only place real network code lives.
# ---------------------------------------------------------------------------

class RealHealthClient:
    """Live probe using stdlib urllib (no extra dependency). A 2xx response is
    ``ok``; timeouts / refused connections / non-2xx are ``ok=False`` with the
    error captured."""

    name = "urllib"

    def probe(self, url: str, timeout: float = 3.0) -> ProbeResult:
        start = time.monotonic()
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", resp.getcode())
                resp.read(2048)  # drain a little so keep-alive closes cleanly
            latency = (time.monotonic() - start) * 1000.0
            ok = 200 <= int(code) < 300
            return ProbeResult(
                ok=ok, http_code=int(code), latency_ms=round(latency, 2),
                error="" if ok else f"HTTP {code}",
            )
        except urllib.error.HTTPError as exc:
            latency = (time.monotonic() - start) * 1000.0
            return ProbeResult(
                ok=False, http_code=exc.code, latency_ms=round(latency, 2),
                error=f"HTTP {exc.code}",
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            latency = (time.monotonic() - start) * 1000.0
            reason = getattr(exc, "reason", exc)
            return ProbeResult(
                ok=False, http_code=0, latency_ms=round(latency, 2),
                error=f"{type(exc).__name__}: {reason}",
            )


def build_health_client(name: Optional[str] = None) -> HealthClient:
    """Factory. Defaults to the real urllib client unless
    EVA_HEALTH_CLIENT=stub (tests force the stub via conftest)."""
    choice = (name or os.environ.get("EVA_HEALTH_CLIENT", "real")).lower()
    if choice == "stub":
        return StubHealthClient()
    return RealHealthClient()
