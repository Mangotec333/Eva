"""Tests for the two-stage SOURCE → SCORE pipeline."""

from pipeline import score_pending, source_deals
from store import SQLiteDealStore


def test_source_then_score_two_stage(store):
    # Stage 1: SOURCE persists raw rows first.
    summary = source_deals(store, "flippa", [
        {"listing_id": "1", "name": "US edu", "category": "education",
         "monthly_net": 4000, "asking_price": 80000, "age_years": 5, "seller_location": "US"},
        {"listing_id": "2", "name": "FR content", "category": "content",
         "monthly_net": 3000, "asking_price": 50000, "seller_location": "FR"},
    ])
    assert summary["new"] == 2
    assert summary["status"] == "completed"
    # Nothing is scored during sourcing.
    assert store.list_scored_deals() == []

    # Stage 2: SCORE reads rows back out of the DB and gates them.
    result = score_pending(store)
    assert result["scored"] == 1
    assert result["skipped"] == 1
    scored = store.list_scored_deals()
    assert len(scored) == 1
    assert scored[0].listing_id == "1"
    assert scored[0].overall_score > 0
    # All 11 composite dimensions carried through.
    for f in ("cashflow_score", "moat_score", "ai_proof_score", "value_add_score",
              "buy_vs_build_score", "risk_score", "mitigation_score",
              "competitor_analysis_score", "company_life_score",
              "owner_neglect_score", "adobe_platform_risk_score"):
        assert hasattr(scored[0], f)


def test_high_trust_bypass_scored(store):
    source_deals(store, "empire_flippers", [
        {"listing_id": "e1", "name": "UK SaaS", "category": "saas",
         "monthly_net": 5000, "multiple": 30, "asking_price": 120000,
         "age_years": 4, "registration_country": "GB"},
    ])
    result = score_pending(store)
    assert result["scored"] == 1
    assert "bypasses US filter" in store.list_scored_deals()[0].gate_reason


def test_score_is_idempotent(store):
    source_deals(store, "flippa", [
        {"listing_id": "1", "name": "US", "monthly_net": 4000,
         "asking_price": 80000, "seller_location": "US"}])
    score_pending(store)
    # Second pass finds nothing pending (already scored) and does not duplicate.
    again = score_pending(store)
    assert again["scored"] == 0
    assert len(store.list_scored_deals()) == 1


def test_closed_comps_ingested_all_geographies_not_scored(store):
    source_deals(store, "bizbuysell", [
        {"listing_id": "c1", "name": "AU sold", "is_closed": True,
         "seller_location": "AU", "sold_price": 100000, "asking_price": 110000},
        {"listing_id": "c2", "name": "DE sold", "is_closed": True,
         "seller_location": "DE", "sold_price": 200000},
    ], mode="backfill")
    closed = store.list_raw_deals(is_closed=True)
    assert len(closed) == 2                # all geographies ingested
    assert score_pending(store)["scored"] == 0   # closed comps never scored
