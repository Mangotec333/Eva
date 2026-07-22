"""Budgeting math: period bounds and spend/income rollups."""

from datetime import date

import budgeting


def test_period_bounds_day():
    ref = date(2026, 7, 15)
    assert budgeting.period_bounds("day", ref) == (ref, ref)


def test_period_bounds_week_monday_anchored():
    # 2026-07-15 is a Wednesday.
    start, end = budgeting.period_bounds("week", date(2026, 7, 15))
    assert start == date(2026, 7, 13)   # Monday
    assert end == date(2026, 7, 19)     # Sunday


def test_period_bounds_month():
    start, end = budgeting.period_bounds("month", date(2026, 7, 15))
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 31)


def test_period_bounds_month_december_rollover():
    start, end = budgeting.period_bounds("month", date(2026, 12, 10))
    assert start == date(2026, 12, 1)
    assert end == date(2026, 12, 31)


def _seed(store):
    acct = store.upsert_account(institution="Chase", name="Checking")
    store.add_transaction(account_id=acct["id"], posted_date="2026-07-05",
                          amount_cents=500000, description="Payroll", category="income")
    store.add_transaction(account_id=acct["id"], posted_date="2026-07-06",
                          amount_cents=-8500, description="Groceries", category="groceries")
    store.add_transaction(account_id=acct["id"], posted_date="2026-07-07",
                          amount_cents=-1500, description="Coffee", category="dining")
    # Outside the July window — must be excluded from July rollups.
    store.add_transaction(account_id=acct["id"], posted_date="2026-06-30",
                          amount_cents=-99999, description="June spend", category="misc")
    return acct


def test_monthly_rollup_math(personal_store):
    _seed(personal_store)
    r = budgeting.rollup(personal_store, "month", ref=date(2026, 7, 15))
    assert r["income_cents"] == 500000
    assert r["spend_cents"] == 10000            # 8500 + 1500, June excluded
    assert r["net_cents"] == 490000
    assert r["transaction_count"] == 3
    assert r["spend_by_category"]["groceries"] == 8500
    assert r["side"] == "personal"


def test_all_rollups_shape(personal_store):
    _seed(personal_store)
    allr = budgeting.all_rollups(personal_store, ref=date(2026, 7, 15))
    assert set(allr) == {"side", "day", "week", "month"}
    assert allr["month"]["spend_cents"] == 10000


def test_empty_store_rollup_is_zero(business_store):
    r = budgeting.rollup(business_store, "month", ref=date(2026, 7, 15))
    assert r["income_cents"] == 0
    assert r["spend_cents"] == 0
    assert r["net_cents"] == 0
