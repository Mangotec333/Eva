"""
EVA Networking-Agent — group discovery providers.

A ``Provider`` returns candidate group dicts for a venture. v1 ships one fully
working, offline provider — ``ManualSeedProvider`` — which ingests a
human/browser-automation-supplied seed list (JSON, CSV, or markdown table).
The platform-specific providers are stubs: they define the interface and raise
``NotImplementedError`` until live network/auth is wired on the Mac side. There
are NO live network calls anywhere in this module — it runs fully offline like
the rest of the codebase.

Candidate dict shape (all optional except name/platform):
    {platform, name, url, member_count, activity_score, topical_fit_score,
     access_type, notes}
``venture_tag`` and ``discovered_via`` are stamped by the service, not here.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Protocol, Union, runtime_checkable

SeedData = Union[str, bytes, list, dict]


@runtime_checkable
class Provider(Protocol):
    name: str
    platform: str

    def discover(self, venture: str, seed_data: SeedData | None = None) -> list[dict]:
        ...


def _coerce_group(raw: dict) -> dict:
    """Normalise one candidate row into the standard group dict shape."""
    def num(*keys, default=0):
        for k in keys:
            if k in raw and raw[k] not in ("", None):
                return raw[k]
        return default

    return {
        "platform": str(raw.get("platform", "") or "").strip(),
        "name": str(raw.get("name", "") or "").strip(),
        "url": str(raw.get("url", "") or "").strip(),
        "member_count": int(float(num("member_count", "members", default=0) or 0)),
        "activity_score": float(num("activity_score", "activity", default=0) or 0),
        "topical_fit_score": float(num("topical_fit_score", "topical_fit", "fit", default=0) or 0),
        "access_type": str(raw.get("access_type", raw.get("access", "public")) or "public").strip().lower(),
        "notes": str(raw.get("notes", "") or "").strip(),
    }


def _parse_markdown_table(text: str) -> list[dict]:
    """Parse a GitHub-style markdown table into row dicts (header-driven)."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # separator row
        rows.append(cells)
    if len(rows) < 2:
        return []
    header = [h.lower().strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
    return out


def parse_seed(seed_data: SeedData) -> list[dict]:
    """Parse seed data (path, raw JSON/CSV/markdown string, list, or dict).

    - list  → treated as rows directly.
    - dict  → ``{"groups": [...]}`` or a single row.
    - str   → an existing file path (extension picks the parser) OR raw content
              sniffed as JSON, then markdown table, then CSV.
    """
    if isinstance(seed_data, bytes):
        seed_data = seed_data.decode("utf-8", "replace")

    if isinstance(seed_data, list):
        return [_coerce_group(r) for r in seed_data if isinstance(r, dict)]
    if isinstance(seed_data, dict):
        rows = seed_data.get("groups")
        if isinstance(rows, list):
            return [_coerce_group(r) for r in rows if isinstance(r, dict)]
        return [_coerce_group(seed_data)]

    if not isinstance(seed_data, str):
        return []

    text = seed_data
    ext = ""
    if len(seed_data) < 4096 and os.path.exists(seed_data):
        ext = Path(seed_data).suffix.lower()
        text = Path(seed_data).read_text(encoding="utf-8")

    stripped = text.lstrip()
    if ext == ".json" or stripped[:1] in ("[", "{"):
        try:
            return parse_seed(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if ext in (".md", ".markdown") or first_line.lstrip().startswith("|"):
        md = _parse_markdown_table(text)
        if md:
            return [_coerce_group(r) for r in md]
    # CSV fallback
    reader = csv.DictReader(io.StringIO(text))
    return [_coerce_group(r) for r in reader if any(v for v in r.values())]


class ManualSeedProvider:
    """v1 provider: ingest a seed list a human or browser run supplies.

    Fully offline and end-to-end functional. Accepts JSON / CSV / markdown
    (file path or raw content) or already-parsed rows.
    """

    name = "manual_seed"
    platform = "manual"

    def discover(self, venture: str, seed_data: SeedData | None = None) -> list[dict]:
        if seed_data is None:
            return []
        return parse_seed(seed_data)


class _LiveProviderStub:
    """Base for not-yet-wired live providers. Documents the contract; never
    performs network I/O in this pass."""

    name = "live_stub"
    platform = "stub"

    def discover(self, venture: str, seed_data: SeedData | None = None) -> list[dict]:
        raise NotImplementedError(
            f"{self.__class__.__name__} live discovery is not wired yet. "
            "Provide seeds via ManualSeedProvider, or configure a live "
            f"{self.platform} integration on the Mac side (subject to platform ToS). "
            "TODO: implement authenticated, ToS-compliant discovery."
        )


class LinkedInGroupsProvider(_LiveProviderStub):
    name = "linkedin_groups"
    platform = "linkedin"


class RedditProvider(_LiveProviderStub):
    name = "reddit"
    platform = "reddit"


class DiscordProvider(_LiveProviderStub):
    name = "discord"
    platform = "discord"


class FacebookGroupsProvider(_LiveProviderStub):
    name = "facebook_groups"
    platform = "facebook"


class ForumProvider(_LiveProviderStub):
    name = "forum"
    platform = "forum"


# Registry: which providers exist and whether they work offline today.
PROVIDERS: dict[str, type] = {
    "manual_seed": ManualSeedProvider,
    "linkedin_groups": LinkedInGroupsProvider,
    "reddit": RedditProvider,
    "discord": DiscordProvider,
    "facebook_groups": FacebookGroupsProvider,
    "forum": ForumProvider,
}


def get_provider(name: str) -> Provider:
    cls = PROVIDERS.get((name or "manual_seed").strip().lower())
    if cls is None:
        raise ValueError(f"unknown provider: {name!r} (have {list(PROVIDERS)})")
    return cls()


__all__ = [
    "Provider", "SeedData", "parse_seed",
    "ManualSeedProvider",
    "LinkedInGroupsProvider", "RedditProvider", "DiscordProvider",
    "FacebookGroupsProvider", "ForumProvider",
    "PROVIDERS", "get_provider",
]
