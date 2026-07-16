"""
EVA IP-Scout — pluggable prior-art provider.

A provider takes a free-text query (an idea's title/abstract) and returns prior-
art hits: ``{"ok", "source", "hits": [{patent_id, title, abstract, date, url}],
"error"?}``. Two implementations ship in v1:

  * ``PatentsViewProvider`` — the PatentsView Search API (config-file-primary key
    from ``credentials.build_cfg``, ``PATENTSVIEW_API_KEY`` env fallback). Every
    call is wrapped so a network/API failure returns an honest ``ok: False`` and
    NEVER crashes the triage run.
  * ``MockPriorArtProvider`` — deterministic offline hits derived from the query,
    used with ``EVA_IP_OFFLINE=1`` and in tests. NO network.

The ``PriorArtProvider`` Protocol keeps this pluggable: USPTO Open Data can be
added in phase-2 by implementing the same interface. Stdlib only (urllib).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, Protocol, runtime_checkable

import credentials

logger = logging.getLogger("ip_scout.provider")

PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with", "by",
    "that", "this", "using", "via", "system", "method", "apparatus", "device",
    "based", "which", "from", "into", "as", "is", "are", "be", "at", "it",
}


def tokenize(text: str) -> list[str]:
    """Lowercase alnum tokens, stopwords + very short tokens removed."""
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


@runtime_checkable
class PriorArtProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 20) -> dict: ...


class MockPriorArtProvider:
    """Offline, deterministic provider — synthesises plausible prior-art hits
    from the query tokens so the whole triage flow is exercisable without a
    network. The hit count scales with how generic the query is (more common
    tokens → more synthetic hits), which lets novelty scoring be tested."""

    name = "mock"

    def __init__(self, hit_map: Optional[dict] = None) -> None:
        # Optional explicit override: {query_substring: [hit, ...]} for tests.
        self.hit_map = hit_map or {}

    def search(self, query: str, *, limit: int = 20) -> dict:
        for key, hits in self.hit_map.items():
            if key.lower() in (query or "").lower():
                return {"ok": True, "source": self.name, "hits": hits[:limit]}

        toks = tokenize(query)
        # Deterministic hit count: derived from a stable hash of the leading
        # tokens, bounded so novelty scoring sees a range of overlaps.
        seed = "-".join(toks[:4])
        n = (sum(ord(c) for c in seed) % 5) if seed else 0
        hits = []
        for i in range(min(n, limit)):
            overlap = toks[: max(1, len(toks) - i)]
            hits.append({
                "patent_id": f"MOCK{abs(hash(seed + str(i))) % 9_000_000 + 1_000_000}",
                "title": f"{' '.join(overlap[:6]).title()} (mock prior art {i + 1})",
                "abstract": f"A mocked prior-art reference covering {' '.join(overlap)}.",
                "date": "2019-01-01",
                "url": "https://patents.example.com/mock",
            })
        return {"ok": True, "source": self.name, "hits": hits}


class PatentsViewProvider:
    """Live provider — queries the PatentsView Search API. Resilient: any
    failure (no key, network, bad response) returns ``ok: False`` with an error
    string; it never raises."""

    name = "patentsview"

    def __init__(self, api_key: str = "", timeout: float = 8.0) -> None:
        self.api_key = api_key or credentials.build_cfg().get("patentsview_api_key", "")
        self.timeout = timeout

    def search(self, query: str, *, limit: int = 20) -> dict:
        if not self.api_key:
            return {"ok": False, "source": self.name, "hits": [],
                    "error": "no PatentsView API key configured"}
        toks = tokenize(query)
        if not toks:
            return {"ok": True, "source": self.name, "hits": []}

        import urllib.error
        import urllib.request

        body = {
            "q": {"_text_any": {"patent_title": " ".join(toks[:12])}},
            "f": ["patent_id", "patent_title", "patent_abstract", "patent_date"],
            "o": {"size": min(limit, 100)},
        }
        req = urllib.request.Request(
            PATENTSVIEW_URL, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Api-Key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode())
            return {"ok": True, "source": self.name,
                    "hits": self._parse_hits(raw, limit)}
        except Exception as exc:  # noqa: BLE001 — resilience is the whole point
            logger.warning("PatentsView query failed: %s", exc)
            return {"ok": False, "source": self.name, "hits": [],
                    "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _parse_hits(raw: dict, limit: int) -> list[dict]:
        """Parse a PatentsView response into normalized hit dicts. Tolerant of
        missing fields / shape drift so a partial response still yields hits."""
        patents = (raw or {}).get("patents") or (raw or {}).get("data", {}).get("patents") or []
        hits = []
        for p in patents[:limit]:
            if not isinstance(p, dict):
                continue
            pid = p.get("patent_id") or p.get("id") or ""
            hits.append({
                "patent_id": str(pid),
                "title": p.get("patent_title") or p.get("title") or "",
                "abstract": p.get("patent_abstract") or p.get("abstract") or "",
                "date": p.get("patent_date") or p.get("date") or "",
                "url": f"https://patents.google.com/patent/US{pid}" if pid else "",
            })
        return hits


def build_provider(offline: Optional[bool] = None,
                   *, hit_map: Optional[dict] = None) -> PriorArtProvider:
    """Offline (or no key) → MockPriorArtProvider; else PatentsViewProvider."""
    import os
    if offline is None:
        offline = os.environ.get("EVA_IP_OFFLINE") == "1"
    if offline:
        return MockPriorArtProvider(hit_map=hit_map)
    key = credentials.build_cfg().get("patentsview_api_key", "")
    if not key:
        # No key → fall back to the offline mock rather than failing every scan.
        return MockPriorArtProvider(hit_map=hit_map)
    return PatentsViewProvider(api_key=key)


__all__ = [
    "PriorArtProvider", "MockPriorArtProvider", "PatentsViewProvider",
    "build_provider", "tokenize", "PATENTSVIEW_URL",
]
