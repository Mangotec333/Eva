"""Tests for 4-lens case-study storage (network-free).

Covers add/list/get, deal_type + pattern filtering, upsert-by-source_url,
nullable deal_id for out-of-box studies, and migration idempotency for the
case_studies table.
"""

from __future__ import annotations

from pipeline_models import CaseStudy, RawDeal


def _deal(store, listing_id: str) -> str:
    d, _ = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id=listing_id, name=f"Deal {listing_id}"))
    return d.id


def _study(**kw) -> CaseStudy:
    base = dict(title="Acme SaaS", source_url="https://example.com/acme",
                deal_type="within_box")
    base.update(kw)
    return CaseStudy(**base)


def test_add_and_get_case_study(store):
    deal_id = _deal(store, "1")
    study = store.add_case_study(_study(
        deal_id=deal_id,
        asking_price=1_200_000, ttm_revenue=800_000, ttm_profit=400_000,
        profit_margin=0.5, profit_multiple=3.0, revenue_multiple=1.5,
        founded_year=2018, customers=1200, team_size=6, location="US",
        usp_summary="Vertical SaaS for dentists",
        lens1_box_fit="Fits the box: profitable, US, SaaS",
        lens2_what_selling="Selling recurring workflow lock-in",
        lens3_juggernaut_arc="Bolt on adjacent modules to 10x",
        lens4_build_vs_buy="Buy: 3yr moat, cheaper than build",
        pattern_tags=["vertical_saas", "workflow_lockin"],
        formula_insight="Boring vertical + switching cost = durable cashflow",
    ))
    assert study.id
    assert study.deal_id == deal_id

    got = store.get_case_study(study.id)
    assert got is not None
    assert got.title == "Acme SaaS"
    assert got.pattern_tags == ["vertical_saas", "workflow_lockin"]
    assert got.profit_multiple == 3.0
    assert got.lens3_juggernaut_arc == "Bolt on adjacent modules to 10x"
    assert got.formula_insight.startswith("Boring vertical")


def test_get_unknown_returns_none(store):
    assert store.get_case_study("no-such-id") is None


def test_list_and_filter_by_deal_type(store):
    store.add_case_study(_study(source_url="https://a.com", deal_type="within_box"))
    store.add_case_study(_study(source_url="https://b.com", deal_type="juggernaut_study"))
    store.add_case_study(_study(source_url="https://c.com",
                                deal_type="build_vs_buy_reference"))

    assert len(store.list_case_studies()) == 3
    jug = store.list_case_studies(deal_type="juggernaut_study")
    assert len(jug) == 1
    assert jug[0].source_url == "https://b.com"


def test_filter_by_pattern_tag(store):
    store.add_case_study(_study(source_url="https://a.com",
                                pattern_tags=["ai_moat", "vertical_saas"]))
    store.add_case_study(_study(source_url="https://b.com",
                                pattern_tags=["marketplace"]))
    hits = store.list_case_studies(pattern="ai_moat")
    assert len(hits) == 1
    assert hits[0].source_url == "https://a.com"
    assert store.list_case_studies(pattern="nonexistent") == []


def test_combined_type_and_pattern_filter(store):
    store.add_case_study(_study(source_url="https://a.com", deal_type="within_box",
                                pattern_tags=["ai_moat"]))
    store.add_case_study(_study(source_url="https://b.com",
                                deal_type="juggernaut_study", pattern_tags=["ai_moat"]))
    hits = store.list_case_studies(deal_type="juggernaut_study", pattern="ai_moat")
    assert len(hits) == 1
    assert hits[0].source_url == "https://b.com"


def test_upsert_by_source_url(store):
    first = store.add_case_study(_study(source_url="https://dup.com",
                                        title="Original", asking_price=100))
    second = store.add_case_study(_study(source_url="https://dup.com",
                                         title="Updated", asking_price=250,
                                         pattern_tags=["revised"]))
    # Same row updated, not duplicated.
    assert first.id == second.id
    all_studies = store.list_case_studies()
    assert len(all_studies) == 1
    assert all_studies[0].title == "Updated"
    assert all_studies[0].asking_price == 250
    assert all_studies[0].pattern_tags == ["revised"]
    assert all_studies[0].created_at == first.created_at


def test_nullable_deal_id_for_out_of_box(store):
    study = store.add_case_study(_study(
        source_url="https://juggernaut.com", deal_id=None,
        deal_type="juggernaut_study", title="Stripe teardown"))
    assert study.deal_id is None
    got = store.get_case_study(study.id)
    assert got.deal_id is None


def test_blank_source_url_studies_not_deduped(store):
    # Out-of-box studies without a URL should each get their own row.
    a = store.add_case_study(_study(source_url="", title="Study A"))
    b = store.add_case_study(_study(source_url="", title="Study B"))
    assert a.id != b.id
    assert len(store.list_case_studies()) == 2


def test_case_study_migration_idempotent(store):
    # store fixture already migrated; re-running applies nothing new.
    assert store.migrate() == []
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "case_studies" in tables
    indexes = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "ux_case_studies_source_url" in indexes
