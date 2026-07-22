"""
EVA Treasurer — categorization rules engine.

Rules are evaluated in ascending ``priority`` (lower first); the first match
wins. Supported ``match_type`` values:

  * ``contains`` — case-insensitive substring match on the description
  * ``exact``    — case-insensitive full-string equality
  * ``regex``    — Python regex search (case-insensitive)

A few sensible built-in rules ship as defaults so a fresh ledger categorizes
common merchants without any setup; DB rules always take precedence over them.
"""

from __future__ import annotations

import re
from typing import Optional

DEFAULT_RULES = [
    {"match_type": "contains", "pattern": "payroll", "category": "income", "priority": 10},
    {"match_type": "contains", "pattern": "invoice", "category": "income", "priority": 10},
    {"match_type": "contains", "pattern": "deposit", "category": "income", "priority": 15},
    {"match_type": "contains", "pattern": "whole foods", "category": "groceries", "priority": 50},
    {"match_type": "contains", "pattern": "trader joe", "category": "groceries", "priority": 50},
    {"match_type": "contains", "pattern": "shell", "category": "fuel", "priority": 50},
    {"match_type": "contains", "pattern": "chevron", "category": "fuel", "priority": 50},
    {"match_type": "contains", "pattern": "aws", "category": "software", "priority": 50},
    {"match_type": "contains", "pattern": "anthropic", "category": "software", "priority": 50},
    {"match_type": "contains", "pattern": "openai", "category": "software", "priority": 50},
    {"match_type": "contains", "pattern": "uber", "category": "transport", "priority": 50},
]


def _matches(match_type: str, pattern: str, description: str) -> bool:
    desc = description.lower()
    pat = pattern.lower()
    if match_type == "contains":
        return pat in desc
    if match_type == "exact":
        return desc == pat
    if match_type == "regex":
        try:
            return re.search(pattern, description, re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def categorize(description: str, rules: list[dict]) -> Optional[str]:
    """Return the category for ``description`` using ``rules`` + defaults.

    DB ``rules`` are tried first (already priority-sorted by the store), then
    the built-in defaults. Returns ``None`` when nothing matches.
    """
    ordered = sorted(rules, key=lambda r: r.get("priority", 100))
    for rule in ordered:
        if _matches(rule["match_type"], rule["pattern"], description):
            return rule["category"]
    for rule in sorted(DEFAULT_RULES, key=lambda r: r["priority"]):
        if _matches(rule["match_type"], rule["pattern"], description):
            return rule["category"]
    return None


def apply_rules_to_store(store) -> int:
    """Re-categorize every ``uncategorized`` transaction on one side's store.

    Returns the number of transactions updated. Operates only on the store's own
    side — separation is preserved because the store is single-side.
    """
    rules = store.list_rules()
    updated = 0
    for txn in store.list_transactions():
        if txn["category"] and txn["category"] != "uncategorized":
            continue
        category = categorize(txn["description"], rules)
        if category:
            store.set_transaction_category(txn["id"], category)
            updated += 1
    return updated
