"""Tests for lightweight 4-lens case-study storage (network-free).

Covers add + retrieve, upsert-by-source_url (refreshing updated_at while
preserving created_at), deal_type filtering, and migration idempotency for the
case_studies table.
"""

from __future__ import annotations

from pipeline_models import RawDeal

SNAPSHOT = {
    "asking": 1_200_000, "revenue": 800_000, "profit": 400_000, "margin": 0.5,
    "profit_multiple": 3.0, "revenue_multiple": 1.5, "founded": 2018,
    "customers": 1200, "team": 6, "location": "US", "usp": "Vertical SaaS for dentists",
}
ANALYSIS = {
    "lens1_box_fit": "Fits the box: profitable, US, SaaS",
    "lens2_what_selling": "Selling recurring workflow lock-in",
    "lens3_juggernaut_arc": "Bolt on adjacent modules to 10x",
    "lens4_build_vs_buy": "Buy: 3yr moat, cheaper than build",
}


def test_add_and_retrieve_case_study(store):
    deal, _ = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id="1", name="Deal 1"))
    study = store.add_case_study(
        source_url="https://example.com/acme",
        deal_type="within_box",
        title="Acme SaaS",
        deal_id=deal.id,
        snapshot=SNAPSHOT,
        analysis=ANALYSIS,
        pattern_tags=["vertical_saas", "workflow_lockin"],
        formula_insight="Boring vertical + switching cost = durable cashflow",
    )
    assert study.id
    assert study.deal_id == deal.id

    got = store.list_case_studies()
    assert len(got) == 1
    row = got[0]
    assert row.title == "Acme SaaS"
    assert row.snapshot["asking"] == 1_200_000
    assert row.analysis["lens3_juggernaut_arc"] == "Bolt on adjacent modules to 10x"
    assert row.pattern_tags == ["vertical_saas", "workflow_lockin"]
    assert row.formula_insight.startswith("Boring vertical")


def test_upsert_by_source_url(store):
    first = store.add_case_study(
        source_url="https://dup.com", deal_type="within_box", title="Original",
        snapshot={"asking": 100})
    second = store.add_case_study(
        source_url="https://dup.com", deal_type="juggernaut_study", title="Updated",
        snapshot={"asking": 250}, pattern_tags=["revised"])

    # Same row updated, not duplicated.
    assert first.id == second.id
    studies = store.list_case_studies()
    assert len(studies) == 1
    row = studies[0]
    assert row.title == "Updated"
    assert row.deal_type == "juggernaut_study"
    assert row.snapshot["asking"] == 250
    assert row.pattern_tags == ["revised"]
    # created_at preserved, updated_at refreshed on the upsert.
    assert row.created_at == first.created_at
    assert second.updated_at >= first.updated_at


def test_filter_by_deal_type(store):
    store.add_case_study(source_url="https://a.com", deal_type="within_box", title="A")
    store.add_case_study(source_url="https://b.com", deal_type="juggernaut_study", title="B")
    store.add_case_study(
        source_url="https://c.com", deal_type="build_vs_buy_reference", title="C")

    assert len(store.list_case_studies()) == 3
    jug = store.list_case_studies(deal_type="juggernaut_study")
    assert len(jug) == 1
    assert jug[0].source_url == "https://b.com"


def test_case_study_migration_idempotent(store):
    # store fixture already migrated; re-running applies nothing new.
    assert store.migrate() == []
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "case_studies" in tables
