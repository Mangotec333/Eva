"""Tests for Empire Flippers ACTIVE (for-sale) listing discovery (public API, mocked).

No network: every test injects a fake ``fetch_page`` returning canned EF API
pages. Verifies active listings land as open deals (``raw_deals`` with
``is_closed=False``), pagination walks all pages, an empty page terminates the
walk, the hard page cap terminates a runaway pull, dedupe holds within a run
and across re-runs, listings that look explicitly sold are skipped, and the EF
monthly multiple is converted to annual (÷12) via the shared adapter.

No ``sale_status``/``status`` param is ever sent by the ingestion function —
every fake ``fetch_page`` asserts it is called with an empty status, matching
the "no filter = active feed" assumption documented in ef_active_listings.py
(flagged there for live-API verification post-deploy).
"""

from __future__ import annotations

from ef_active_listings import (
    MAX_PAGE_HARD_CAP,
    ef_active_listing_to_payload,
    ingest_ef_active_listings,
)
from pipeline import score_pending


def _ef_page(listings, *, total_pages=1):
    """Build an EF-API-shaped page: listings as a stringified-index dict."""
    listings_block = {str(i): obj for i, obj in enumerate(listings)}
    return {"data": {"pagination": {"total_pages": total_pages},
                     "listings": listings_block}}


def _active(listing_number, **over):
    base = {
        "listing_number": listing_number,
        "status": "For Sale",
        "monetization": "SaaS",
        "monthly_net_profit": 6000,
        "multiple": 36,             # EF monthly multiple → 3.0 annual
        "listing_price": 216000,
        "business_location": "US",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def test_listing_maps_the_expected_open_deal_fields():
    payload = ef_active_listing_to_payload(_active("70999", monetization="Ecommerce"))
    assert payload["source"] == "empire_flippers"
    assert payload["listing_id"] == "70999"
    assert payload["url"].endswith("/listing/70999/")
    assert payload["is_closed"] is False
    assert payload["market_status"] == "available"
    assert "sold_price" not in payload
    assert "sold_at" not in payload
    assert payload["monthly_profit"] == 6000
    assert payload["multiple"] == 36           # raw monthly; adapter divides by 12
    assert payload["asking_price"] == 216000
    assert payload["seller_location"] == "US"
    assert payload["category"]                  # niche/monetization carried through


# ---------------------------------------------------------------------------
# Ingestion → open raw_deals set
# ---------------------------------------------------------------------------

def test_ingest_writes_active_rows_as_open_deals(store):
    pages = {1: _ef_page([_active("1"), _active("2")], total_pages=1)}
    result = ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: pages[p])

    assert result["active_found"] == 2
    assert result["new"] == 2
    open_deals = store.list_raw_deals(is_closed=False, source="empire_flippers")
    assert len(open_deals) == 2
    row = open_deals[0]
    assert row.is_closed is False
    assert row.source == "empire_flippers"
    # EF monthly multiple (36) normalized to annual (÷12 = 3.0).
    assert row.annual_multiple == 3.0


def test_no_status_filter_is_ever_sent_to_the_api():
    pages = {1: _ef_page([_active("1")], total_pages=1)}
    calls: list[tuple[int, int, str]] = []

    def fetch(page, per_page, status):
        calls.append((page, per_page, status))
        return pages[page]

    from store import SQLiteDealStore
    s = SQLiteDealStore(":memory:")
    s.migrate()
    try:
        ingest_ef_active_listings(s, fetch_page=fetch)
    finally:
        s.close()
    assert calls == [(1, 100, "")]           # empty status = no sale_status/status param


def test_ingested_active_listings_are_scored_like_any_open_deal(store):
    pages = {1: _ef_page([_active("1", business_location="US")], total_pages=1)}
    ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: pages[p])
    # Unlike closed comps, active listings are real open candidates and DO
    # enter the scorer (empire_flippers is high-trust, bypasses the US filter
    # anyway, but this one is also US-located).
    assert score_pending(store)["scored"] == 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_walks_every_page(store):
    pages = {
        1: _ef_page([_active("1"), _active("2")], total_pages=3),
        2: _ef_page([_active("3"), _active("4")], total_pages=3),
        3: _ef_page([_active("5")], total_pages=3),
    }
    calls: list[int] = []

    def fetch(page, per_page, status):
        calls.append(page)
        return pages[page]

    result = ingest_ef_active_listings(store, fetch_page=fetch)
    assert calls == [1, 2, 3]           # walked all three pages, then stopped
    assert result["pages_fetched"] == 3
    assert result["active_found"] == 5
    assert len(store.list_raw_deals(is_closed=False)) == 5


def test_pagination_stops_on_empty_page(store):
    pages = {
        1: _ef_page([_active("1")], total_pages=99),   # lies about total_pages
        2: _ef_page([], total_pages=99),               # empty → stop
    }
    result = ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: pages[p])
    assert result["pages_fetched"] == 2
    assert result["active_found"] == 1


def test_max_pages_caps_the_pull(store):
    pages = {p: _ef_page([_active(str(p))], total_pages=10) for p in range(1, 11)}
    result = ingest_ef_active_listings(
        store, fetch_page=lambda p, pp, st: pages[p], max_pages=2)
    assert result["pages_fetched"] == 2
    assert result["active_found"] == 2


def test_hard_page_cap_terminates_a_runaway_total_pages(store):
    # total_pages lies (way beyond the hard cap) and every page returns a
    # listing, so only the MAX_PAGE_HARD_CAP safety net can stop the walk.
    calls: list[int] = []

    def fetch(page, per_page, status):
        calls.append(page)
        return _ef_page([_active(f"p{page}")], total_pages=MAX_PAGE_HARD_CAP * 10)

    result = ingest_ef_active_listings(store, fetch_page=fetch)
    assert result["pages_fetched"] == MAX_PAGE_HARD_CAP
    assert len(calls) == MAX_PAGE_HARD_CAP
    assert max(calls) == MAX_PAGE_HARD_CAP


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

def test_dedupe_within_a_single_run(store):
    # Same listing number appears on two pages — counted once.
    pages = {
        1: _ef_page([_active("dup"), _active("a")], total_pages=2),
        2: _ef_page([_active("dup"), _active("b")], total_pages=2),
    }
    result = ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: pages[p])
    assert result["active_found"] == 3          # dup collapsed
    assert len(store.list_raw_deals(is_closed=False)) == 3


def test_dedupe_across_reruns_is_idempotent(store):
    pages = {1: _ef_page([_active("1"), _active("2")], total_pages=1)}
    fetch = lambda p, pp, st: pages[p]

    first = ingest_ef_active_listings(store, fetch_page=fetch)
    assert first["new"] == 2
    second = ingest_ef_active_listings(store, fetch_page=fetch)
    assert second["new"] == 0                 # nothing new on re-run
    assert second["updated"] == 2             # existing rows refreshed in place
    assert len(store.list_raw_deals(is_closed=False)) == 2


# ---------------------------------------------------------------------------
# Safety-net sold filter (in case the "no filter" assumption is ever wrong)
# ---------------------------------------------------------------------------

def test_explicitly_sold_listings_are_skipped_as_a_safety_net(store):
    page = _ef_page([
        _active("open-1"),
        {"listing_number": "sold-1", "status": "Sold", "sold_price": 90000,
         "monthly_net_profit": 3000, "multiple": 30, "listing_price": 90000},
    ], total_pages=1)
    result = ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: page)
    assert result["active_found"] == 1
    assert result["skipped_not_active"] == 1
    open_deals = store.list_raw_deals(is_closed=False)
    assert len(open_deals) == 1
    assert open_deals[0].listing_id == "open-1"


def test_listings_as_plain_array_shape_is_accepted(store):
    # Some API responses return listings as a JSON array rather than an
    # index-keyed dict — both must ingest.
    resp = {"data": {"pagination": {"total_pages": 1},
                     "listings": [_active("arr-1"), _active("arr-2")]}}
    result = ingest_ef_active_listings(store, fetch_page=lambda p, pp, st: resp)
    assert result["active_found"] == 2
    assert len(store.list_raw_deals(is_closed=False)) == 2


def test_no_payloads_returns_a_zeroed_summary(store):
    result = ingest_ef_active_listings(
        store, fetch_page=lambda p, pp, st: _ef_page([], total_pages=1))
    assert result["active_found"] == 0
    assert result["new"] == 0
    assert "note" in result
