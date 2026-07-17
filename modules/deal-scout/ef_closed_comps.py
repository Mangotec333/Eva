"""
EVA Deal Scout — Empire Flippers CLOSED/sold comps ingestion (public API).

Pulls SOLD listings from Empire Flippers' public API and writes them into the
same ``raw_deals`` closed-comps set (``is_closed=True``) the rest of the pipeline
already uses.  The closed-comps set was previously ~92 rows, mostly Flippa; EF
sold comps de-bias it with a high-trust marketplace.

Why this module exists separately from ``scrapers/empire_flippers.py``:
    * that scraper fetches ONE *open* listing by HTML scraping;
    * this module pages the public JSON API for MANY *sold* comps.

Design (pure + testable, matching the rest of the pipeline)
----------------------------------------------------------
* The network fetch is a single injectable seam (``fetch_page``) — tests pass a
  fake that returns canned API pages, so no test touches the network.
* Every EF listing is mapped to a payload dict the existing ``empire_flippers``
  source adapter already understands (``_norm_ef`` → monthly multiple ÷ 12,
  ``is_closed`` / ``sold_price`` handling), then routed through
  ``pipeline.source_deals`` so the normal dedupe + snapshot + source_run
  bookkeeping applies.  Re-running is idempotent: ``upsert_raw_deal`` dedupes on
  ``(source, dedupe_key)`` where the key is the EF listing number.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from pipeline import source_deals
from store import DealStore

EF_API_URL = "https://api.empireflippers.com/api/v1/listings/list"
EF_SOURCE = "empire_flippers"
DEFAULT_PER_PAGE = 100
# Hard cap so a bad ``total_pages`` can never spin forever.
MAX_PAGE_HARD_CAP = 500

# A page fetcher is (page, per_page, status) -> parsed-json-dict. Injectable for
# tests so the API shape is exercised without any network access.
PageFetcher = Callable[[int, int, str], dict]


# ---------------------------------------------------------------------------
# API response shape helpers
# ---------------------------------------------------------------------------

def _listings_from_response(resp: dict) -> list[dict]:
    """Extract the listing objects from one EF API page.

    EF wraps listings under ``data.listings``.  Historically that value is a
    dict keyed by stringified indices (``{"0": {...}, "1": {...}}``) rather than
    a JSON array, so we accept either shape.  Any non-listing siblings (e.g. a
    ``pagination`` key that some responses nest here) are dropped.
    """
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    listings = data.get("listings", data) if isinstance(data, dict) else data
    if isinstance(listings, list):
        return [x for x in listings if isinstance(x, dict)]
    if isinstance(listings, dict):
        out = []
        for key, val in listings.items():
            if key == "pagination":
                continue
            if isinstance(val, dict):
                out.append(val)
        return out
    return []


def _total_pages(resp: dict) -> Optional[int]:
    """Best-effort total-page count from the EF pagination block."""
    if not isinstance(resp, dict):
        return None
    data = resp.get("data", resp)
    pag = {}
    if isinstance(data, dict):
        pag = data.get("pagination") or {}
        if not pag and isinstance(data.get("listings"), dict):
            pag = data["listings"].get("pagination") or {}
    for key in ("total_pages", "pages", "last_page", "page_count"):
        val = pag.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    return None


def _is_sold(listing: dict) -> bool:
    """True when an EF listing represents a closed/sold comp."""
    status = str(
        listing.get("status")
        or listing.get("listing_status")
        or listing.get("sale_status")
        or ""
    ).lower()
    if any(w in status for w in ("sold", "closed")):
        return True
    return bool(
        listing.get("sold_price")
        or listing.get("sale_price")
        or listing.get("date_sold")
        or listing.get("sold_at")
    )


# ---------------------------------------------------------------------------
# EF listing -> pipeline payload
# ---------------------------------------------------------------------------

def ef_listing_to_payload(listing: dict) -> dict:
    """Map one EF API listing into a payload the ``empire_flippers`` adapter reads.

    Only keys the adapter's ``_base_raw`` normalizer understands are set; the
    untouched listing is preserved via ``raw_json`` for audit.  ``multiple`` is
    left as EF's monthly multiple — the adapter divides it by 12.
    """
    listing_number = str(
        listing.get("listing_number")
        or listing.get("listing_id")
        or listing.get("id")
        or ""
    ).strip()
    url = str(listing.get("url") or listing.get("listing_url") or "").strip()
    if not url and listing_number:
        url = f"https://empireflippers.com/listing/{listing_number}/"

    category = str(
        listing.get("monetization")
        or listing.get("niche")
        or listing.get("category")
        or listing.get("business_type")
        or ""
    )

    monthly_net = (
        listing.get("monthly_net_profit")
        or listing.get("average_monthly_net_profit")
        or listing.get("monthly_profit")
        or listing.get("monthly_net")
        or 0
    )
    multiple = (
        listing.get("multiple")
        or listing.get("listing_multiple")
        or listing.get("monthly_multiple")
        or 0
    )
    sold_price = (
        listing.get("sold_price")
        or listing.get("sale_price")
        or 0
    )
    asking_price = (
        listing.get("listing_price")
        or listing.get("asking_price")
        or listing.get("price")
        or sold_price
        or 0
    )
    sold_at = str(
        listing.get("date_sold")
        or listing.get("sold_at")
        or listing.get("sold_date")
        or ""
    )
    geography = str(
        listing.get("business_location")
        or listing.get("seller_location")
        or listing.get("country")
        or listing.get("location")
        or ""
    )

    return {
        "source": EF_SOURCE,
        "listing_id": listing_number,
        "url": url,
        "name": str(
            listing.get("listing_title")
            or listing.get("title")
            or listing.get("name")
            or (f"Empire Flippers #{listing_number}" if listing_number else "EF sold listing")
        )[:200],
        "category": category,
        "monthly_profit": monthly_net,
        "multiple": multiple,
        "sale_price": sold_price,
        "sold_price": sold_price,
        "asking_price": asking_price,
        "sold_at": sold_at,
        "seller_location": geography,
        "country": geography,
        "currency": str(listing.get("currency") or "USD"),
        "is_closed": True,
        "status": "sold",
        "market_status": "sold",
        "raw_json": json.dumps(listing, default=str),
    }


# ---------------------------------------------------------------------------
# Default network fetcher (stdlib urllib — no 3rd-party dep)
# ---------------------------------------------------------------------------

def _default_fetch_page(page: int, per_page: int, status: str,
                        *, timeout: float = 20.0) -> dict:
    import urllib.parse
    import urllib.request

    params = {"page": page, "per_page": per_page}
    if status:
        # EF filters sold comps by sale status; the client-side _is_sold guard
        # is the safety net if the param name differs across API versions.
        params["sale_status"] = status
        params["status"] = status
    url = f"{EF_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "EVA-DealScout/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted url)
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Public ingestion entrypoint
# ---------------------------------------------------------------------------

def ingest_ef_closed_comps(
    store: DealStore,
    *,
    fetch_page: Optional[PageFetcher] = None,
    per_page: int = DEFAULT_PER_PAGE,
    max_pages: Optional[int] = None,
    status: str = "sold",
) -> dict[str, Any]:
    """Page the EF public API for SOLD listings and ingest them as closed comps.

    Pagination: pages are pulled until a page returns no listings, the reported
    ``total_pages`` is reached, or ``max_pages`` is hit.  Only listings that pass
    ``_is_sold`` are kept.  All collected payloads are ingested in a single
    ``source_deals`` run so dedupe (by EF listing number) happens across pages
    and against existing ``closed_comps`` rows in one pass.
    """
    fetch = fetch_page or (lambda p, pp, st: _default_fetch_page(p, pp, st))
    store.migrate()

    payloads: list[dict] = []
    seen_keys: set[str] = set()
    pages_fetched = 0
    total_pages: Optional[int] = None
    skipped_not_sold = 0

    page = 1
    hard_cap = min(max_pages or MAX_PAGE_HARD_CAP, MAX_PAGE_HARD_CAP)
    while page <= hard_cap:
        resp = fetch(page, per_page, status)
        pages_fetched += 1
        if total_pages is None:
            total_pages = _total_pages(resp)

        listings = _listings_from_response(resp)
        if not listings:
            break

        for listing in listings:
            if not _is_sold(listing):
                skipped_not_sold += 1
                continue
            payload = ef_listing_to_payload(listing)
            # In-batch dedupe so the same comp on two pages isn't double-counted.
            key = payload.get("listing_id") or payload.get("url")
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            payloads.append(payload)

        if total_pages is not None and page >= total_pages:
            break
        if max_pages is not None and pages_fetched >= max_pages:
            break
        page += 1

    if not payloads:
        return {
            "source": EF_SOURCE,
            "mode": "ef_closed_comps",
            "pages_fetched": pages_fetched,
            "sold_found": 0,
            "new": 0,
            "updated": 0,
            "skipped_not_sold": skipped_not_sold,
            "note": "no sold comps returned by the EF API",
        }

    summary = source_deals(store, EF_SOURCE, payloads, mode="ef_closed_comps")
    return {
        "source": EF_SOURCE,
        "mode": "ef_closed_comps",
        "source_run_id": summary["source_run_id"],
        "pages_fetched": pages_fetched,
        "sold_found": len(payloads),
        "new": summary["new"],
        "updated": summary["updated"],
        "snapshots": summary["snapshots"],
        "skipped_not_sold": skipped_not_sold,
        "status": summary["status"],
    }


__all__ = [
    "EF_API_URL",
    "EF_SOURCE",
    "ingest_ef_closed_comps",
    "ef_listing_to_payload",
]
