"""Tests for the review ``status`` / ``pass_reason`` pair (network-free).

Covers the enum validation on the pydantic models, the 400-guard helper the API
uses when a deal is marked passed, the additive ``deals`` column migration
against a plain sqlite3 connection, and the pass-reason grouping helper.
"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from deals_schema import (
    DEAL_COLUMN_MIGRATIONS,
    group_passed_deals,
    migrate_deals_table,
    pending_deal_column_sql,
)
from models import PASS_REASONS, VALID_STATUS, Deal, DealUpdate, pass_reason_error

DEAL_KWARGS = dict(
    id="d1", source="acquire_com", listing_id="l1", url="https://example.test/l1",
    name="Deal", category="SaaS", monthly_net=1_000, annual_multiple=3.0,
    asking_price=36_000, age_years=2.0,
)

# The original CREATE, before status/pass_reason shipped.
LEGACY_DEALS_SQL = """
CREATE TABLE deals (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'tracking'
)
"""


def test_pass_reason_enum_validation():
    assert PASS_REASONS, "the enum must offer at least one structured reason"

    for reason in PASS_REASONS:
        assert DealUpdate(status="passed", pass_reason=reason).pass_reason == reason
        assert Deal(**DEAL_KWARGS, status="passed", pass_reason=reason).pass_reason == reason

    # An unknown reason is rejected by both models.
    for model in (DealUpdate, Deal):
        with pytest.raises(ValidationError, match="pass_reason must be one of"):
            model(**({} if model is DealUpdate else DEAL_KWARGS), pass_reason="vibes")

    # None (and the empty string) are allowed and normalize to None — a deal can
    # be updated without touching its rejection reason.
    assert DealUpdate(pass_reason=None).pass_reason is None
    assert DealUpdate(pass_reason="").pass_reason is None
    assert Deal(**DEAL_KWARGS).pass_reason is None


def test_status_enum_validation_and_default():
    assert VALID_STATUS == ["active", "passed"]
    assert Deal(**DEAL_KWARGS).status == "active"
    assert Deal(**DEAL_KWARGS, status="passed").status == "passed"
    assert DealUpdate(status=None).status is None

    with pytest.raises(ValidationError, match="status must be one of"):
        DealUpdate(status="rejected")
    with pytest.raises(ValidationError, match="status must be one of"):
        Deal(**DEAL_KWARGS, status="archived")

    # status is orthogonal to the stage pipeline — passing a deal leaves it be.
    passed = Deal(**DEAL_KWARGS, status="passed", pass_reason=PASS_REASONS[0])
    assert passed.stage == "tracking"


def test_pass_reason_error_guard():
    # Only status="passed" with no reason is an error.
    msg = pass_reason_error("passed", None)
    assert msg and "pass_reason is required" in msg
    assert all(reason in msg for reason in PASS_REASONS)
    assert pass_reason_error("passed", "") == msg

    assert pass_reason_error("passed", PASS_REASONS[0]) is None
    assert pass_reason_error("active", None) is None
    assert pass_reason_error(None, None) is None
    # A pass_reason with no status change (e.g. an unrelated PUT) is fine.
    assert pass_reason_error(None, PASS_REASONS[0]) is None


def test_deals_table_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(LEGACY_DEALS_SQL)

        applied = migrate_deals_table(conn)
        assert applied == [sql for _, sql in DEAL_COLUMN_MIGRATIONS]

        cols = {r[1] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
        assert {"status", "pass_reason"} <= cols

        # Second run is a no-op.
        assert migrate_deals_table(conn) == []
        assert pending_deal_column_sql(cols) == []

        # Existing rows land on the 'active' default with no reason.
        conn.execute("INSERT INTO deals (id, name) VALUES ('old', 'Legacy')")
        row = conn.execute("SELECT status, pass_reason FROM deals WHERE id='old'").fetchone()
        assert row == ("active", None)
    finally:
        conn.close()


def test_group_passed_deals_counts_and_ordering():
    deals = [
        {"id": "a", "pass_reason": "price_too_high"},
        {"id": "b", "pass_reason": "churn_too_high"},
        {"id": "c", "pass_reason": "price_too_high"},
        {"id": "d", "pass_reason": None},
        {"id": "e"},
        {"id": "f", "pass_reason": ""},
    ]
    grouped = group_passed_deals(deals)

    assert grouped["total"] == 6
    # Most common reason first; None / missing / "" all fall into "unspecified".
    assert list(grouped["reason_counts"]) == [
        "unspecified", "price_too_high", "churn_too_high"]
    assert grouped["reason_counts"] == {
        "unspecified": 3, "price_too_high": 2, "churn_too_high": 1}

    assert [g["pass_reason"] for g in grouped["groups"]] == list(grouped["reason_counts"])
    assert [g["count"] for g in grouped["groups"]] == [3, 2, 1]
    assert [d["id"] for d in grouped["groups"][0]["deals"]] == ["d", "e", "f"]
    assert [d["id"] for d in grouped["groups"][1]["deals"]] == ["a", "c"]

    empty = group_passed_deals([])
    assert empty == {"total": 0, "reason_counts": {}, "groups": []}


def test_group_passed_deals_breaks_count_ties_alphabetically():
    grouped = group_passed_deals([
        {"id": "1", "pass_reason": "thin_moat"},
        {"id": "2", "pass_reason": "churn_too_high"},
    ])
    assert list(grouped["reason_counts"]) == ["churn_too_high", "thin_moat"]
