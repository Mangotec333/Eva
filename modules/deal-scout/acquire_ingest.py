"""
EVA Deal Scout — reusable Acquire.com listing ingest.

Acquire.com is gated (no public scrape API), so listings arrive as a manually
saved JSON blob rather than a feed fetch.  This module runs that blob through
the same normalize → score → persist pipeline as every other source, tagged
``source=acquire_com``, and optionally attaches researched competitor intel and
a case study in the same call.

Used by ``cli.py ingest-acquire`` and by the per-listing scripts under
``scripts/`` so a new Acquire.com listing never needs a new one-off script.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from pipeline import score_raw_deal, source_deals
from sources import listing_id_from_url
from store import DealStore

SOURCE = "acquire_com"


def load_listing(path: str) -> dict:
    """Read a manually-saved Acquire.com listing JSON file."""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a single listing object, got {type(payload).__name__}")
    return payload


def ingest_listing(
    store: DealStore,
    payload: dict,
    *,
    url: str = "",
    force_score: bool = True,
    competitors: Optional[Sequence[dict]] = None,
    case_study: Optional[dict] = None,
    analyzer_kwargs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Normalize → score → persist one Acquire.com listing.

    ``url`` overrides/fills the listing URL (the CLI's ``--url`` flag); the
    listing id is derived from it the same way every other adapter does.
    ``force_score`` defaults to True because Acquire.com is a medium-trust,
    frequently non-US marketplace that the automated gate would otherwise skip
    — the gate verdict is still recorded on the scored row either way.
    """
    payload = dict(payload)
    if url:
        payload["url"] = url
    listing_url = payload.get("url", "")
    if not listing_url:
        raise ValueError("an Acquire.com listing needs a url (pass --url or set it in the JSON)")
    # Same identity rule the adapter applies: the URL tail wins over any
    # explicit id, so the lookup below matches what source_deals just wrote.
    listing_id = listing_id_from_url(listing_url) or str(payload.get("listing_id", ""))

    summary = source_deals(store, SOURCE, [payload])

    raw = store.find_raw_deal(SOURCE, listing_id, listing_url)
    if raw is None:
        raise ValueError(f"listing {listing_id!r} was not persisted by the source stage")

    scoring = score_raw_deal(store, raw, force=force_score, **(analyzer_kwargs or {}))

    added_competitors = 0
    for competitor in competitors or []:
        store.add_competitor(deal_id=raw.id, **competitor)
        added_competitors += 1

    case_study_id = ""
    if case_study:
        cs = dict(case_study)
        cs.setdefault("source_url", listing_url)
        cs.setdefault("deal_id", raw.id)
        case_study_id = store.add_case_study(**cs).id

    return {
        "source": SOURCE,
        "url": listing_url,
        "listing_id": listing_id,
        "raw_deal_id": raw.id,
        "source_run_id": summary["source_run_id"],
        "is_new": summary["new"] == 1,
        "scoring": scoring,
        "competitors_added": added_competitors,
        "case_study_id": case_study_id,
    }
