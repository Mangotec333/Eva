"""Tests for competitor-intelligence storage (network-free).

Covers add/list, competitor dedupe across deals (same entity, multiple links),
blank-field compounding, moat_comparison refresh, and migration idempotency for
the competitor tables.
"""

from __future__ import annotations

from pipeline_models import RawDeal


def _deal(store, listing_id: str) -> str:
    d, _ = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id=listing_id, name=f"Deal {listing_id}"))
    return d.id


def test_add_and_list_competitor(store):
    deal_id = _deal(store, "1")
    comp = store.add_competitor(
        deal_id=deal_id,
        name="CrowdStrike",
        what_they_do="Endpoint detection and response",
        pricing_model="Per-endpoint annual subscription",
        url="https://crowdstrike.com",
        moat_comparison="Deal has a narrower vertical focus",
        source_url="https://example.com/research",
        category="cybersecurity",
    )
    assert comp.id
    assert comp.name == "CrowdStrike"
    assert comp.moat_comparison == "Deal has a narrower vertical focus"

    comps = store.list_competitors(deal_id)
    assert len(comps) == 1
    assert comps[0].name == "CrowdStrike"
    assert comps[0].what_they_do == "Endpoint detection and response"
    assert comps[0].category == "cybersecurity"
    assert comps[0].moat_comparison == "Deal has a narrower vertical focus"


def test_same_competitor_links_to_multiple_deals(store):
    deal_a = _deal(store, "a")
    deal_b = _deal(store, "b")

    c1 = store.add_competitor(deal_id=deal_a, name="CrowdStrike",
                              what_they_do="EDR", moat_comparison="A angle")
    c2 = store.add_competitor(deal_id=deal_b, name="CrowdStrike",
                              moat_comparison="B angle")

    # One shared entity, two distinct links.
    assert c1.id == c2.id
    entity_rows = store.conn.execute("SELECT COUNT(*) FROM competitors").fetchone()[0]
    link_rows = store.conn.execute("SELECT COUNT(*) FROM deal_competitors").fetchone()[0]
    assert entity_rows == 1
    assert link_rows == 2

    # moat_comparison is per-link, not shared.
    assert store.list_competitors(deal_a)[0].moat_comparison == "A angle"
    assert store.list_competitors(deal_b)[0].moat_comparison == "B angle"
    # what_they_do compounded from deal_a is visible on deal_b's link too.
    assert store.list_competitors(deal_b)[0].what_they_do == "EDR"


def test_name_dedupe_is_case_insensitive(store):
    deal_id = _deal(store, "c")
    store.add_competitor(deal_id=deal_id, name="CrowdStrike")
    store.add_competitor(deal_id=deal_id, name="  crowdstrike ")
    assert store.conn.execute("SELECT COUNT(*) FROM competitors").fetchone()[0] == 1
    # Re-linking the same competitor to the same deal is idempotent.
    assert len(store.list_competitors(deal_id)) == 1


def test_compounding_fills_blanks_without_clobbering(store):
    deal_id = _deal(store, "d")
    store.add_competitor(deal_id=deal_id, name="Okta",
                         what_they_do="Identity platform", pricing_model="")
    # Second call fills the blank pricing_model but must not overwrite what_they_do.
    store.add_competitor(deal_id=deal_id, name="Okta",
                         what_they_do="SOMETHING ELSE",
                         pricing_model="Per-user/month")
    comp = store.list_competitors(deal_id)[0]
    assert comp.what_they_do == "Identity platform"
    assert comp.pricing_model == "Per-user/month"


def test_moat_comparison_refreshes_on_relink(store):
    deal_id = _deal(store, "e")
    store.add_competitor(deal_id=deal_id, name="Zscaler", moat_comparison="v1")
    store.add_competitor(deal_id=deal_id, name="Zscaler", moat_comparison="v2")
    assert store.list_competitors(deal_id)[0].moat_comparison == "v2"


def test_empty_name_rejected(store):
    deal_id = _deal(store, "f")
    try:
        store.add_competitor(deal_id=deal_id, name="   ")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for blank competitor name")


def test_list_competitors_empty_for_unknown_deal(store):
    assert store.list_competitors("no-such-deal") == []


def test_competitor_migration_idempotent(store):
    # store fixture already migrated; re-running applies nothing new.
    assert store.migrate() == []
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "competitors" in tables
    assert "deal_competitors" in tables
    indexes = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "ux_competitors_name_key" in indexes
    assert "ux_deal_competitors_pair" in indexes
