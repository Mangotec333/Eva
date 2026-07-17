"""Tests for Empire Flippers CLOSED/sold comps ingestion (public API, mocked).

No network: every test injects a fake ``fetch_page`` returning canned EF API
pages.  Verifies sold comps land in the closed-comps set (``raw_deals`` with
``is_closed=True``), pagination walks all pages, dedupe holds within a run and
across re-runs, non-sold listings are dropped, and the EF monthly multiple is
converted to annual (÷12).
"""

from __future__ import annotations

from ef_closed_comps import ef_listing_to_payload, ingest_ef_closed_comps
from pipeline import score_pending


def _ef_page(listings, *, total_pages=1):
    """Build an EF-API-shaped page: listings as a stringified-index dict."""
    listings_block = {str(i): obj for i, obj in enumerate(listings)}
    return {"data": {"pagination": {"total_pages": total_pages},
                     "listings": listings_block}}


def _sold(listing_number, **over):
    base = {
        "listing_number": listing_number,
        "status": "Sold",
        "monetization": "SaaS",
        "monthly_net_profit": 5000,
        "multiple": 30,             # EF monthly multiple → 2.5 annual
        "listing_price": 150000,
        "sold_price": 145000,
        "date_sold": "2026-05-01",
        "business_location": "US",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def test_listing_maps_the_expected_closed_comp_fields():
    payload = ef_listing_to_payload(_sold("70123", monetization="Ecommerce"))
    assert payload["source"] == "empire_flippers"
    assert payload["listing_id"] == "70123"
    assert payload["url"].endswith("/listing/70123/")
    assert payload["is_closed"] is True
    assert payload["market_status"] == "sold"
    assert payload["sale_price"] == 145000
    assert payload["monthly_profit"] == 5000
    assert payload["multiple"] == 30           # raw monthly; adapter divides by 12
    assert payload["seller_location"] == "US"
    assert payload["category"]                  # niche/monetization carried through


# ---------------------------------------------------------------------------
# Ingestion → closed_comps set
# ---------------------------------------------------------------------------

def test_ingest_writes_sold_rows_into_closed_comps(store):
    pages = {1: _ef_page([_sold("1"), _sold("2")], total_pages=1)}
    result = ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: pages[p])

    assert result["sold_found"] == 2
    assert result["new"] == 2
    closed = store.list_raw_deals(is_closed=True, source="empire_flippers")
    assert len(closed) == 2
    row = closed[0]
    assert row.is_closed is True
    assert row.source == "empire_flippers"
    assert row.sold_price == 145000
    # EF monthly multiple (30) normalized to annual (÷12 = 2.5).
    assert row.annual_multiple == 2.5


def test_ingested_ef_closed_comps_are_never_scored(store):
    pages = {1: _ef_page([_sold("1", business_location="US"),
                          _sold("2", business_location="DE")], total_pages=1)}
    ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: pages[p])
    # Closed comps are ingested for all geographies but never enter the scorer.
    assert score_pending(store)["scored"] == 0


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_walks_every_page(store):
    pages = {
        1: _ef_page([_sold("1"), _sold("2")], total_pages=3),
        2: _ef_page([_sold("3"), _sold("4")], total_pages=3),
        3: _ef_page([_sold("5")], total_pages=3),
    }
    calls: list[int] = []

    def fetch(page, per_page, status):
        calls.append(page)
        return pages[page]

    result = ingest_ef_closed_comps(store, fetch_page=fetch)
    assert calls == [1, 2, 3]           # walked all three pages, then stopped
    assert result["pages_fetched"] == 3
    assert result["sold_found"] == 5
    assert len(store.list_raw_deals(is_closed=True)) == 5


def test_pagination_stops_on_empty_page(store):
    pages = {
        1: _ef_page([_sold("1")], total_pages=99),   # lies about total_pages
        2: _ef_page([], total_pages=99),             # empty → stop
    }
    result = ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: pages[p])
    assert result["pages_fetched"] == 2
    assert result["sold_found"] == 1


def test_max_pages_caps_the_pull(store):
    pages = {p: _ef_page([_sold(str(p))], total_pages=10) for p in range(1, 11)}
    result = ingest_ef_closed_comps(
        store, fetch_page=lambda p, pp, st: pages[p], max_pages=2)
    assert result["pages_fetched"] == 2
    assert result["sold_found"] == 2


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

def test_dedupe_within_a_single_run(store):
    # Same listing number appears on two pages — counted once.
    pages = {
        1: _ef_page([_sold("dup"), _sold("a")], total_pages=2),
        2: _ef_page([_sold("dup"), _sold("b")], total_pages=2),
    }
    result = ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: pages[p])
    assert result["sold_found"] == 3          # dup collapsed
    assert len(store.list_raw_deals(is_closed=True)) == 3


def test_dedupe_across_reruns_is_idempotent(store):
    pages = {1: _ef_page([_sold("1"), _sold("2")], total_pages=1)}
    fetch = lambda p, pp, st: pages[p]

    first = ingest_ef_closed_comps(store, fetch_page=fetch)
    assert first["new"] == 2
    second = ingest_ef_closed_comps(store, fetch_page=fetch)
    assert second["new"] == 0                 # nothing new on re-run
    assert second["updated"] == 2             # existing rows refreshed in place
    assert len(store.list_raw_deals(is_closed=True)) == 2


# ---------------------------------------------------------------------------
# Sold filter
# ---------------------------------------------------------------------------

def test_non_sold_listings_are_skipped(store):
    page = _ef_page([
        _sold("sold-1"),
        {"listing_number": "open-1", "status": "For Sale",
         "monthly_net_profit": 4000, "multiple": 40, "listing_price": 200000},
    ], total_pages=1)
    result = ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: page)
    assert result["sold_found"] == 1
    assert result["skipped_not_sold"] == 1
    closed = store.list_raw_deals(is_closed=True)
    assert len(closed) == 1
    assert closed[0].listing_id == "sold-1"


def test_listings_as_plain_array_shape_is_accepted(store):
    # Some API responses return listings as a JSON array rather than an
    # index-keyed dict — both must ingest.
    resp = {"data": {"pagination": {"total_pages": 1},
                     "listings": [_sold("arr-1"), _sold("arr-2")]}}
    result = ingest_ef_closed_comps(store, fetch_page=lambda p, pp, st: resp)
    assert result["sold_found"] == 2
    assert len(store.list_raw_deals(is_closed=True)) == 2
