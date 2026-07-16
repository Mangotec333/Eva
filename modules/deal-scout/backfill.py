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
from sources import ADAPTERS, SEEDS
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
    src = str(obj.get("source") or default).strip().lower().replace(" ", "_").replace(".", "")
    aliases = {
        "ef": "empire_flippers", "empireflippers": "empire_flippers",
        "acquirecom": "acquire", "acquire_com": "acquire",
        "bizbuysell": "bizbuysell",
    }
    src = aliases.get(src, src)
    if src in ADAPTERS:
        return src
    # Unknown/seed sources fall back to a live generic-normalizing adapter so
    # the row still lands in the DB; trust level defaults to the seed's or low.
    return src if src in SEEDS else default


def backfill_open(
    store: DealStore,
    data_dir: str = "deal_scout_data",
    default_source: str = "flippa",
) -> dict[str, Any]:
    """Import every ``*.json`` under ``data_dir`` as open listings."""
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
            obj.setdefault("is_closed", False)
            src = _resolve_source(obj, default_source)
            by_source.setdefault(src, []).append(obj)
        for src, payloads in by_source.items():
            if src not in ADAPTERS:
                src = default_source  # seed-only sources cannot scrape/normalize yet
            results.append({"file": os.path.basename(path),
                            **source_deals(store, src, payloads, mode="backfill")})

    return {"imported_files": len(files), "runs": results}


def backfill_closed(
    store: DealStore,
    path: str = "closed_deals_dataset.json",
    default_source: str = "flippa",
) -> dict[str, Any]:
    """Import closed/sold comps (all geographies, no US filter)."""
    if not os.path.isfile(path):
        return {"imported": 0, "note": f"{path!r} not present — skipped", "runs": []}

    objs = _iter_deal_objects(_load_json(path))
    by_source: dict[str, list[dict]] = {}
    for obj in objs:
        obj["is_closed"] = True
        if not obj.get("market_status"):
            obj["market_status"] = "sold"
        src = _resolve_source(obj, default_source)
        if src not in ADAPTERS:
            src = default_source
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
