"""Tests for the DealStore + migrations layer."""

from pipeline_models import DealSnapshot, RawDeal, TrendReport


def test_migrations_are_idempotent(store):
    # Re-running migrate applies nothing the second time.
    assert store.migrate() == []
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("source_runs", "raw_deals", "deal_snapshots", "scored_deals",
              "trend_reports", "schema_migrations"):
        assert t in tables


def test_upsert_dedupes_by_source_and_key(store):
    d1, created1 = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id="1", name="A", monthly_net=10))
    assert created1 is True
    d2, created2 = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id="1", name="A v2", monthly_net=99))
    assert created2 is False
    assert d2.id == d1.id
    assert d2.monthly_net == 99
    # Different source with same listing_id is a distinct row.
    _, created3 = store.upsert_raw_deal(
        RawDeal(id="", source="acquire_com", listing_id="1", name="B"))
    assert created3 is True
    assert len(store.list_raw_deals()) == 2


def test_dedupe_key_falls_back_to_url(store):
    d, created = store.upsert_raw_deal(
        RawDeal(id="", source="flippa", listing_id="", url="https://x/y/"))
    assert created is True
    assert d.dedupe_key == "https://x/y"  # trailing slash stripped


def test_timestamps_are_stamped(store):
    d, _ = store.upsert_raw_deal(RawDeal(id="", source="flippa", listing_id="ts"))
    assert d.created_at and d.updated_at and d.sourced_at


def test_financial_verification_backfills_from_source(store):
    # Acquire.com: unaudited seller self-listing -> "self_reported" by default.
    acquire, _ = store.upsert_raw_deal(
        RawDeal(id="", source="acquire_com", listing_id="a1", name="A"))
    assert acquire.financial_verification == "self_reported"

    # Empire Flippers independently audits bank statements -> "verified".
    ef, _ = store.upsert_raw_deal(
        RawDeal(id="", source="empire_flippers", listing_id="e1", name="E"))
    assert ef.financial_verification == "verified"

    # An explicit non-"unknown" tag is never overridden by the backfill.
    manual, _ = store.upsert_raw_deal(
        RawDeal(id="", source="acquire_com", listing_id="a2", name="A2",
                financial_verification="advisor_reviewed"))
    assert manual.financial_verification == "advisor_reviewed"

    # verified_only filter keeps EF + the advisor-reviewed Acquire deal, drops
    # the plain self-reported Acquire deal.
    kept = {d.listing_id for d in store.list_raw_deals(verified_only=True)}
    assert kept == {"e1", "a2"}


def test_snapshots_and_source_runs(store):
    run = store.start_source_run("flippa", "Flippa")
    assert run.status == "running"
    d, _ = store.upsert_raw_deal(RawDeal(id="", source="flippa", listing_id="s"))
    store.add_snapshot(DealSnapshot(id="", raw_deal_id=d.id, market_status="available",
                                    asking_price=100, monthly_net=10))
    run.status = "completed"
    run.deals_found = 1
    store.finish_source_run(run)
    runs = store.list_source_runs()
    assert runs[0].status == "completed" and runs[0].finished_at
    assert len(store.list_snapshots(d.id)) == 1


def test_trend_report_roundtrip(store):
    r = store.save_trend_report(TrendReport(id="", report_md="# hi", stats_json="{}"))
    assert store.latest_trend_report().id == r.id
