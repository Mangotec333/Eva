"""Bill due-date tracking + credit utilization threshold alert tests."""

from datetime import date

import bills as bills_engine


def test_utilization_threshold_flags_high_card(personal_store):
    # 42% utilization — above the 30% default => alert.
    personal_store.upsert_account(institution="Amex", name="Gold",
                                  account_type="credit_card",
                                  credit_limit_cents=1000000, balance_cents=420000)
    # 10% utilization — below threshold => no alert.
    personal_store.upsert_account(institution="Visa", name="Everyday",
                                  account_type="credit_card",
                                  credit_limit_cents=1000000, balance_cents=100000)
    report = bills_engine.utilization_report(personal_store, threshold=0.30)
    assert report["alert_count"] == 1
    assert report["alerts"][0]["name"] == "Gold"
    assert report["alerts"][0]["utilization"] == 0.42
    # overall = 520000 / 2000000 = 0.26
    assert report["overall_utilization"] == 0.26


def test_utilization_exactly_at_threshold_is_flagged(personal_store):
    personal_store.upsert_account(institution="Amex", name="AtLimit",
                                  account_type="credit_card",
                                  credit_limit_cents=1000000, balance_cents=300000)
    report = bills_engine.utilization_report(personal_store, threshold=0.30)
    assert report["alert_count"] == 1  # 0.30 >= 0.30


def test_custom_threshold(personal_store):
    personal_store.upsert_account(institution="Amex", name="Card",
                                  account_type="credit_card",
                                  credit_limit_cents=1000000, balance_cents=250000)
    assert bills_engine.utilization_report(personal_store, threshold=0.30)["alert_count"] == 0
    assert bills_engine.utilization_report(personal_store, threshold=0.20)["alert_count"] == 1


def test_non_credit_accounts_ignored(personal_store):
    personal_store.upsert_account(institution="Chase", name="Checking",
                                  account_type="checking", balance_cents=999999)
    report = bills_engine.utilization_report(personal_store)
    assert report["cards"] == []
    assert report["overall_utilization"] == 0.0


def test_upcoming_bills_horizon_and_overdue(personal_store):
    acct = personal_store.upsert_account(institution="Amex", name="Gold",
                                         account_type="credit_card",
                                         credit_limit_cents=1000000, balance_cents=1000)
    ref = date(2026, 7, 15)
    personal_store.add_bill(account_id=acct["id"], name="overdue",
                            due_date="2026-07-10", minimum_payment_cents=3500)
    personal_store.add_bill(account_id=acct["id"], name="soon",
                            due_date="2026-07-20", minimum_payment_cents=4000)
    personal_store.add_bill(account_id=acct["id"], name="far",
                            due_date="2026-09-30", minimum_payment_cents=5000)
    upcoming = bills_engine.upcoming_bills(personal_store, within_days=30, ref=ref)
    names = [b["name"] for b in upcoming]
    assert names == ["overdue", "soon"]        # "far" excluded, sorted by date
    assert upcoming[0]["overdue"] is True
    assert upcoming[0]["days_until_due"] == -5
    assert upcoming[1]["overdue"] is False
