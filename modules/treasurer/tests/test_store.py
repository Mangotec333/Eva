"""Data model + dedup + separation-at-the-store-layer tests."""

import pytest


def _acct(store):
    return store.upsert_account(institution="Chase", name="Checking",
                                account_type="checking")


def test_account_upsert_is_idempotent(personal_store):
    a1 = _acct(personal_store)
    a2 = personal_store.upsert_account(institution="Chase", name="Checking",
                                       account_type="savings", balance_cents=999)
    assert a1["id"] == a2["id"]
    assert len(personal_store.list_accounts()) == 1
    assert personal_store.get_account(a1["id"])["balance_cents"] == 999


def test_transaction_insert_and_fetch(personal_store):
    acct = _acct(personal_store)
    res = personal_store.add_transaction(
        account_id=acct["id"], posted_date="2026-07-01",
        amount_cents=-1500, description="Coffee")
    assert res["inserted"] is True
    txn = res["transaction"]
    assert txn["side"] == "personal"
    assert txn["amount_cents"] == -1500
    assert personal_store.get_transaction(txn["id"])["description"] == "Coffee"


def test_dedup_by_derived_key(personal_store):
    acct = _acct(personal_store)
    kw = dict(account_id=acct["id"], posted_date="2026-07-01",
              amount_cents=-1500, description="Coffee")
    first = personal_store.add_transaction(**kw)
    second = personal_store.add_transaction(**kw)
    assert first["inserted"] is True
    assert second["inserted"] is False
    assert first["transaction"]["id"] == second["transaction"]["id"]
    assert len(personal_store.list_transactions()) == 1


def test_dedup_by_explicit_key(personal_store):
    acct = _acct(personal_store)
    a = personal_store.add_transaction(account_id=acct["id"], posted_date="2026-07-01",
                                       amount_cents=-100, description="A", dedup_key="k1")
    # Different fields but same explicit dedup_key => treated as duplicate.
    b = personal_store.add_transaction(account_id=acct["id"], posted_date="2026-07-09",
                                       amount_cents=-999, description="B", dedup_key="k1")
    assert a["inserted"] is True
    assert b["inserted"] is False
    assert len(personal_store.list_transactions()) == 1


def test_transaction_requires_known_account(personal_store):
    with pytest.raises(ValueError):
        personal_store.add_transaction(account_id="nope", posted_date="2026-07-01",
                                       amount_cents=-1, description="x")


def test_cross_side_write_is_blocked(personal_store):
    # A record explicitly labeled "business" must be rejected by a personal store.
    with pytest.raises(ValueError):
        personal_store.upsert_account(institution="X", name="Y", side="business")


def test_credit_accounts_filter(personal_store):
    personal_store.upsert_account(institution="Chase", name="Checking",
                                  account_type="checking")
    personal_store.upsert_account(institution="Amex", name="Card",
                                  account_type="credit_card", credit_limit_cents=500000)
    cards = personal_store.credit_accounts()
    assert len(cards) == 1
    assert cards[0]["name"] == "Card"


def test_invalid_side_rejected():
    from store import TreasurerStore
    with pytest.raises(ValueError):
        TreasurerStore("household", ":memory:")
