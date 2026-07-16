"""
EVA Deal Scout — backfill importer.

Imports pre-existing on-disk datasets into the DB-backed pipeline:

  * ``deal_scout_data/*.json``   — open/tracked listings (one deal per object,
    or a top-level ``{"deals": [...]}`` wrapper).
  * ``closed_deals_dataset.json`` — closed/sold comps (ingested for ALL
    geographies, marked ``is_closed=True``).

Everything is routed through ``pipeline.source_deals`` so the same dedupe,
snapshotting and source_run bookkeeping applies.  Missing files are skipped
gracefully (these datasets are gitignored runtime data, so they may be absent
in a fresh checkout).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Optional

from pipeline import source_deals
from sources import ADAPTERS, SEEDS, canonical_source
from store import DealStore


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _iter_deal_objects(data: Any) -> list[dict]:
    """Accept a list, a {"deals": [...]} wrapper, or a single object."""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("deals", "listings", "items", "results"):
            if isinstance(data.get(key), list):
                return [d for d in data[key] if isinstance(d, dict)]
        return [data]
    return []


def _resolve_source(obj: dict, default: str) -> str:
    """Canonicalize the source label (source/marketplace/platform) to an adapter key."""
    label = obj.get("source") or obj.get("marketplace") or obj.get("platform") or default
    src = canonical_source(str(label), default)
    if src in ADAPTERS:
        return src
    # Unknown/seed sources cannot normalize yet — route through the generic
    # default adapter so the row still lands in the DB.
    return default


def _is_closed_record(obj: dict) -> bool:
    status = str(obj.get("status") or obj.get("market_status") or "").lower()
    return bool(obj.get("is_closed") or obj.get("sold") or status in ("sold", "closed"))


def backfill_open(
    store: DealStore,
    data_dir: str = "deal_scout_data",
    default_source: str = "flippa",
) -> dict[str, Any]:
    """Import every ``*.json`` under ``data_dir`` as open listings.

    Records flagged closed/sold are skipped here — closed comps are owned by
    ``backfill_closed`` so a unified file carrying both stays single-sourced.
    """
    results: list[dict] = []
    if not os.path.isdir(data_dir):
        return {"imported_files": 0, "note": f"{data_dir!r} not present — skipped", "runs": []}

    files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    for path in files:
        try:
            objs = _iter_deal_objects(_load_json(path))
        except (json.JSONDecodeError, OSError) as exc:
            results.append({"file": path, "error": str(exc)})
            continue
        # Group by resolved source so each source_run is single-source.
        by_source: dict[str, list[dict]] = {}
        for obj in objs:
            if _is_closed_record(obj):
                continue
            obj.setdefault("is_closed", False)
            src = _resolve_source(obj, default_source)
            by_source.setdefault(src, []).append(obj)
        for src, payloads in by_source.items():
            results.append({"file": os.path.basename(path),
                            **source_deals(store, src, payloads, mode="backfill")})

    return {"imported_files": len(files), "runs": results}


def backfill_closed(
    store: DealStore,
    path: str = "closed_deals_dataset.json",
    default_source: str = "flippa",
) -> dict[str, Any]:
    """Import closed/sold comps (all geographies, no US filter).

    Closed comps share a generic ``source_url`` (e.g. a marketplace's
    closed-deals landing page), so a stable per-record dedupe id is synthesized
    from the file position to keep all comps distinct and re-import idempotent.
    """
    if not os.path.isfile(path):
        return {"imported": 0, "note": f"{path!r} not present — skipped", "runs": []}

    objs = _iter_deal_objects(_load_json(path))
    by_source: dict[str, list[dict]] = {}
    for i, obj in enumerate(objs):
        obj = dict(obj)
        obj["is_closed"] = True
        if not obj.get("market_status"):
            obj["market_status"] = "sold"
        src = _resolve_source(obj, default_source)
        # Force a unique, stable dedupe key: blank every URL alias (comps share
        # a generic landing-page URL) and stamp a positional listing_id so the
        # normalizer keeps each comp as its own distinct row.
        obj["url"] = obj["listing_url"] = obj["source_url"] = ""
        obj["listing_id"] = obj["deal_id"] = obj["id"] = f"closed-{src}-{i}"
        by_source.setdefault(src, []).append(obj)

    runs = [source_deals(store, src, payloads, mode="backfill")
            for src, payloads in by_source.items()]
    return {"imported": len(objs), "runs": runs}


def backfill_all(
    store: DealStore,
    data_dir: str = "deal_scout_data",
    closed_path: str = "closed_deals_dataset.json",
) -> dict[str, Any]:
    return {
        "open": backfill_open(store, data_dir),
        "closed": backfill_closed(store, closed_path),
    }
