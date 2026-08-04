"""
EVA Deal Scout — Empire Flippers ACTIVE (for-sale) listing discovery (public API).

Pulls currently-listed (for-sale) listings from Empire Flippers' public API and
writes them into the normal open-deal pipeline (``raw_deals`` with
``is_closed=False``) so they flow through ``score_pending`` and the deal box
the same as any other sourced listing. This is what makes Deal Scout capable
of *discovering* new candidates on a schedule instead of requiring a manual
listing ID to be handed to ``/deals/fetch/ef/{listing_id}``.

Mirrors ``ef_closed_comps.py`` (same pagination / dedupe / injectable-fetch
seam) but is aimed at the opposite slice of the EF catalog: active listings
instead of sold comps.

*** IMPORTANT — UNVERIFIED ASSUMPTION, CHECK AGAINST THE LIVE API AFTER DEPLOY ***
This sandbox has no internet access, so the real shape of the EF public API's
default (unfiltered) response has never actually been observed here. The
working assumption baked into this module is:

    Calling ``GET /api/v1/listings/list`` with NO ``sale_status``/``status``
    filter returns the marketplace's default listing feed, which is assumed to
    be the currently ACTIVE / for-sale listings (as opposed to sold/closed
    ones, which appear to require an explicit ``status=sold`` filter per
    ``ef_closed_comps.py``).

This assumption must be verified against the real, live API response once this
module is deployed to a host with internet access. If it turns out the
unfiltered feed actually mixes active + sold listings (or defaults to sold),
this module's ``_looks_active`` guard is the safety net that filters out
anything that looks closed/sold — but the pagination totals and page contents
should still be spot-checked manually against empireflippers.com's live
marketplace listing count after the first scheduled run in production.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from pipeline import source_deals
from store import DealStore

EF_API_URL = "https://api.empireflippers.com/api/v1/listings/list"
EF_SOURCE = "empire_flippers"
DEFAULT_PER_PAGE = 100
# Hard cap so a bad ``total_pages`` can never spin forever (same safety pattern
# as ef_closed_comps.py).
MAX_PAGE_HARD_CAP = 500

# A page fetcher is (page, per_page, status) -> parsed-json-dict. Injectable for
# tests so the API shape is exercised without any network access. ``status`` is
# threaded through for symmetry with ef_closed_comps.PageFetcher, but active
# discovery always calls with status="" (no sale-status filter applied).
PageFetcher = Callable[[int, int, str], dict]


# ---------------------------------------------------------------------------
# API response shape helpers (identical extraction logic to ef_closed_comps —
# duplicated rather than imported so this module has no import-time coupling
# to the closed-comps module and each can evolve independently).
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


def _looks_sold(listing: dict) -> bool:
    """True when a listing explicitly looks closed/sold.

    Safety-net filter for the "no status filter" assumption above: even if the
    unfiltered feed unexpectedly includes sold listings, we never want to route
    an obviously-sold listing into the *active* discovery path.
    """
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


def _looks_active(listing: dict) -> bool:
    """True unless the listing explicitly looks sold/closed (see module docstring)."""
    return not _looks_sold(listing)


# ---------------------------------------------------------------------------
# EF listing -> pipeline payload
# ---------------------------------------------------------------------------

def ef_active_listing_to_payload(listing: dict) -> dict:
    """Map one EF API listing into a payload the ``empire_flippers`` adapter reads.

    Same field mapping as ``ef_closed_comps.ef_listing_to_payload`` except the
    listing is always marked open (``is_closed=False``), no sold_price/sold_at
    is set, and ``market_status="available"``. ``multiple`` is left as EF's
    monthly multiple — the adapter divides it by 12.
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
    asking_price = (
        listing.get("listing_price")
        or listing.get("asking_price")
        or listing.get("price")
        or 0
    )
    geography = str(
        listing.get("business_location")
        or listing.get("seller_location")
        or listing.get("country")
        or listing.get("location")
        or ""
    )
    age_years = (
        listing.get("age_years")
        or listing.get("age")
        or 0
    )

    return {
        "source": EF_SOURCE,
        "listing_id": listing_number,
        "url": url,
        "name": str(
            listing.get("listing_title")
            or listing.get("title")
            or listing.get("name")
            or (f"Empire Flippers #{listing_number}" if listing_number else "EF active listing")
        )[:200],
        "category": category,
        "monthly_profit": monthly_net,
        "multiple": multiple,
        "asking_price": asking_price,
        "age_years": age_years,
        "seller_location": geography,
        "country": geography,
        "currency": str(listing.get("currency") or "USD"),
        "is_closed": False,
        "status": "available",
        "market_status": "available",
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
    # NOTE (assumption under live verification — see module docstring): we
    # deliberately omit any sale_status/status params here. The working
    # assumption is that EF's default/unfiltered feed returns active (for
    # sale) listings. ``status`` is accepted for interface symmetry with
    # ef_closed_comps' fetcher but intentionally unused when empty.
    if status:
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

def ingest_ef_active_listings(
    store: DealStore,
    *,
    fetch_page: Optional[PageFetcher] = None,
    per_page: int = DEFAULT_PER_PAGE,
    max_pages: Optional[int] = None,
) -> dict[str, Any]:
    """Page the EF public API for ACTIVE listings and ingest them as open deals.

    No ``sale_status``/``status`` filter is sent (see the "UNVERIFIED
    ASSUMPTION" note in the module docstring) — ``fetch_page`` is always called
    with ``status=""``. Pagination: pages are pulled until a page returns no
    listings, the reported ``total_pages`` is reached, or ``max_pages``/the
    ``MAX_PAGE_HARD_CAP`` safety cap is hit. Listings that look explicitly sold
    are skipped as a safety net. All collected payloads are ingested in a
    single ``source_deals`` run so dedupe (by EF listing number) happens across
    pages and against existing open ``raw_deals`` rows in one pass.
    """
    fetch = fetch_page or (lambda p, pp, st: _default_fetch_page(p, pp, st))
    store.migrate()

    payloads: list[dict] = []
    seen_keys: set[str] = set()
    pages_fetched = 0
    total_pages: Optional[int] = None
    skipped_not_active = 0

    page = 1
    hard_cap = min(max_pages or MAX_PAGE_HARD_CAP, MAX_PAGE_HARD_CAP)
    while page <= hard_cap:
        # status="" — no sale_status/status filter sent to the API (assumption
        # under live verification, see module docstring).
        resp = fetch(page, per_page, "")
        pages_fetched += 1
        if total_pages is None:
            total_pages = _total_pages(resp)

        listings = _listings_from_response(resp)
        if not listings:
            break

        for listing in listings:
            if not _looks_active(listing):
                skipped_not_active += 1
                continue
            payload = ef_active_listing_to_payload(listing)
            # In-batch dedupe so the same listing on two pages isn't double-counted.
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
            "mode": "ef_active_listings",
            "pages_fetched": pages_fetched,
            "active_found": 0,
            "new": 0,
            "updated": 0,
            "skipped_not_active": skipped_not_active,
            "note": "no active listings returned by the EF API",
        }

    summary = source_deals(store, EF_SOURCE, payloads, mode="ef_active_listings")
    return {
        "source": EF_SOURCE,
        "mode": "ef_active_listings",
        "source_run_id": summary["source_run_id"],
        "pages_fetched": pages_fetched,
        "active_found": len(payloads),
        "new": summary["new"],
        "updated": summary["updated"],
        "snapshots": summary["snapshots"],
        "skipped_not_active": skipped_not_active,
        "status": summary["status"],
    }


__all__ = [
    "EF_API_URL",
    "EF_SOURCE",
    "MAX_PAGE_HARD_CAP",
    "ingest_ef_active_listings",
    "ef_active_listing_to_payload",
]
