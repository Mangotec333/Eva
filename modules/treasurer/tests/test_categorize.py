"""Categorization rule engine tests."""

from categorize import apply_rules_to_store, categorize


def test_default_rules_match():
    assert categorize("Whole Foods Market #123", []) == "groceries"
    assert categorize("SHELL OIL 4455", []) == "fuel"
    assert categorize("ACME Payroll July", []) == "income"


def test_no_match_returns_none():
    assert categorize("Mystery merchant xyz", []) is None


def test_db_rule_priority_beats_default():
    rules = [{"match_type": "contains", "pattern": "shell",
              "category": "business_fuel", "priority": 1}]
    # DB rule (priority 1) wins over the default fuel rule (priority 50).
    assert categorize("Shell Gas", rules) == "business_fuel"


def test_exact_and_regex_match():
    exact = [{"match_type": "exact", "pattern": "netflix", "category": "streaming", "priority": 5}]
    assert categorize("Netflix", exact) == "streaming"
    assert categorize("Netflix subscription", exact) is None

    rgx = [{"match_type": "regex", "pattern": r"amzn?\s*mktp", "category": "shopping", "priority": 5}]
    assert categorize("AMZN Mktp US*2X", rgx) == "shopping"


def test_bad_regex_is_safe():
    rules = [{"match_type": "regex", "pattern": "([", "category": "x", "priority": 1}]
    assert categorize("anything", rules) is None


def test_apply_rules_to_store(personal_store):
    acct = personal_store.upsert_account(institution="Chase", name="Checking")
    personal_store.add_transaction(account_id=acct["id"], posted_date="2026-07-01",
                                   amount_cents=-8500, description="Whole Foods")
    personal_store.add_transaction(account_id=acct["id"], posted_date="2026-07-02",
                                   amount_cents=-1000, description="Unknown vendor zzz")
    updated = apply_rules_to_store(personal_store)
    assert updated == 1
    cats = {t["description"]: t["category"] for t in personal_store.list_transactions()}
    assert cats["Whole Foods"] == "groceries"
    assert cats["Unknown vendor zzz"] == "uncategorized"
