"""Tests for the reusable Acquire.com ingest path (network-free).

Acquire.com is a gated marketplace, so a listing arrives as a manually saved
JSON blob.  These cover the ``cli.py ingest-acquire`` command end-to-end against
a temp DB: normalize → force-score → persist, plus the ``--no-force-score``
variant where the gate's skip verdict stands.
"""

from __future__ import annotations

import json

import pytest

import cli
from acquire_ingest import SOURCE, ingest_listing, load_listing
from store import SQLiteDealStore

STARTUP_ID = "97MLWWoUHSPPFjqsZv88RemyCrM2"
URL = f"https://app.acquire.com/startup/{STARTUP_ID}/eF646qqNwAsFhwXoOwtr"
# Identity follows the shared adapter rule: the URL tail wins over any explicit
# listing_id in the payload, so re-ingesting the same URL updates in place.
LISTING_ID = "eF646qqNwAsFhwXoOwtr"

LISTING = {
    "listing_id": STARTUP_ID,
    "name": "UK SaaS — Talent Vetting",
    "category": "SaaS",
    "monthly_net": 1_450.0,
    "annual_multiple": 11.8,
    "asking_price": 204_600.0,
    "age_years": 2.83,
    "registration_country": "GB",
    "seller_location": "United Kingdom",
    "ttm_revenue": 122_300.0,
    "ttm_profit": 17_400.0,
    "last_month_net": 371.0,
    "monthly_churn": 0.075,
}


@pytest.fixture()
def listing_file(tmp_path):
    path = tmp_path / "listing.json"
    path.write_text(json.dumps(LISTING), encoding="utf-8")
    return str(path)


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "ingest.db")


def _run_cli(db_path: str, *args: str) -> int:
    return cli.main(["--db", db_path, "ingest-acquire", *args])


def test_cli_ingest_acquire_persists_and_scores(db_path, listing_file, capsys):
    assert _run_cli(db_path, "--url", URL, "--raw-json", listing_file) == 0
    out = json.loads(capsys.readouterr().out)

    assert out["source"] == SOURCE
    assert out["listing_id"] == LISTING_ID
    assert out["url"] == URL
    assert out["is_new"] is True
    assert out["scoring"]["status"] == "scored"

    store = SQLiteDealStore(db_path)
    try:
        raw = store.find_raw_deal(SOURCE, LISTING_ID, URL)
        assert raw is not None
        assert raw.id == out["raw_deal_id"]
        assert raw.source == SOURCE
        assert raw.asking_price == LISTING["asking_price"]
        # The digital-micro inputs survive into raw_json for the box evaluator.
        payload = json.loads(raw.raw_json)
        assert payload["monthly_churn"] == 0.075
        assert payload["ttm_revenue"] == 122_300.0

        scored = [s for s in store.list_scored_deals() if s.raw_deal_id == raw.id]
        assert len(scored) == 1
        assert scored[0].source == SOURCE
        assert 0.0 <= scored[0].overall_score <= 10.0
    finally:
        store.close()


def test_cli_ingest_acquire_forces_past_the_gate(db_path, listing_file, capsys):
    """A non-US gated listing is force-scored, with the gate verdict recorded."""
    _run_cli(db_path, "--url", URL, "--raw-json", listing_file)
    out = json.loads(capsys.readouterr().out)

    scoring = out["scoring"]
    assert scoring["forced"] is True
    assert scoring["reason"]  # the would-be skip reason is preserved

    store = SQLiteDealStore(db_path)
    try:
        scored = store.list_scored_deals()[0]
        assert scored.skip_reason == "manual_score_gate_would_skip"
        assert scored.gate_reason == scoring["reason"]
        raw = store.get_raw_deal(out["raw_deal_id"])
        assert raw.gate_status == "scored"
    finally:
        store.close()


def test_cli_ingest_acquire_respects_the_gate_when_asked(db_path, listing_file, capsys):
    assert _run_cli(db_path, "--url", URL, "--raw-json", listing_file,
                    "--no-force-score") == 0
    out = json.loads(capsys.readouterr().out)

    assert out["scoring"]["status"] == "skipped"
    store = SQLiteDealStore(db_path)
    try:
        assert store.list_scored_deals() == []
        raw = store.get_raw_deal(out["raw_deal_id"])
        assert raw.gate_status == "skipped"
        assert raw.skip_reason
    finally:
        store.close()


def test_cli_ingest_acquire_reingest_updates_in_place(db_path, listing_file, capsys):
    _run_cli(db_path, "--url", URL, "--raw-json", listing_file)
    first = json.loads(capsys.readouterr().out)

    _run_cli(db_path, "--url", URL, "--raw-json", listing_file)
    second = json.loads(capsys.readouterr().out)

    assert second["is_new"] is False
    assert second["raw_deal_id"] == first["raw_deal_id"]

    store = SQLiteDealStore(db_path)
    try:
        assert len(store.list_raw_deals()) == 1
    finally:
        store.close()


def test_cli_ingest_acquire_reports_bad_input(db_path, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert _run_cli(db_path, "--url", URL, "--raw-json", str(bad)) == 0
    assert "expected a single listing object" in json.loads(capsys.readouterr().out)["error"]

    assert _run_cli(db_path, "--url", URL, "--raw-json", str(tmp_path / "nope.json")) == 0
    assert json.loads(capsys.readouterr().out)["error"]

    # A listing with no URL anywhere cannot be identified.
    no_url = tmp_path / "no_url.json"
    no_url.write_text(json.dumps(LISTING), encoding="utf-8")
    assert _run_cli(db_path, "--raw-json", str(no_url)) == 0
    assert "needs a url" in json.loads(capsys.readouterr().out)["error"]


def test_ingest_listing_attaches_competitors_and_case_study(store, listing_file):
    """The per-listing scripts' extra intel rides along on the same call."""
    payload = load_listing(listing_file)
    result = ingest_listing(
        store, payload, url=URL,
        competitors=[dict(name="Toptal", what_they_do="Vetted freelancers",
                          url="https://www.toptal.com/", category="Services")],
        case_study={"deal_type": "within_box", "title": "Acquire listing",
                    "pattern_tags": ["uk_seller"]},
        analyzer_kwargs={"num_competitors": 1, "revenue_declining": True},
    )

    assert result["competitors_added"] == 1
    assert result["case_study_id"]

    comps = store.list_competitors(result["raw_deal_id"])
    assert [c.name for c in comps] == ["Toptal"]

    studies = store.list_case_studies(deal_type="within_box")
    assert any(s.id == result["case_study_id"] and s.deal_id == result["raw_deal_id"]
               for s in studies)
