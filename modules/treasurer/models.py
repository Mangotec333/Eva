"""
EVA Treasurer — Pydantic models.

Money is always stored and passed as integer cents (never floats) to avoid
rounding drift, matching the ``amount_cents`` convention used by the
finance-tracker module.

Amount sign convention for transactions:
  * negative cents  = money OUT  (spend / debit)
  * positive cents  = money IN   (income / credit)

Personal vs. business separation is structural, not a column filter: each
``side`` lives in its own SQLite database file (see ``store.py``). ``side`` is
still carried on every model so API responses and CLI output are clearly
labeled.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

VALID_SIDES = ["personal", "business"]
VALID_ACCOUNT_TYPES = ["checking", "savings", "credit_card", "loan", "cash", "investment"]

# Account types that carry a credit limit and are subject to utilization checks.
CREDIT_ACCOUNT_TYPES = ["credit_card"]

DEFAULT_UTILIZATION_THRESHOLD = 0.30


class Account(BaseModel):
    id: str
    side: str                                   # "personal" | "business"
    institution: str                            # e.g. "Chase", "Amex"
    name: str                                   # human label, e.g. "Sapphire Reserve"
    account_type: str = "checking"              # see VALID_ACCOUNT_TYPES
    external_id: str = ""                       # provider-side id, used for upsert
    credit_limit_cents: int = 0                 # >0 only for cards / lines of credit
    balance_cents: int = 0                      # current balance (owed, for a card)
    currency: str = "USD"
    created_at: str = ""
    updated_at: str = ""


class Transaction(BaseModel):
    id: str
    side: str
    account_id: str
    posted_date: str                            # ISO date, YYYY-MM-DD
    amount_cents: int                           # signed; negative = spend
    description: str = ""
    category: str = "uncategorized"
    dedup_key: str = ""                         # stable per-account idempotency key
    provider: str = "manual"
    created_at: str = ""


class CategorizationRule(BaseModel):
    id: str
    side: str
    match_type: str = "contains"                # "contains" | "exact" | "regex"
    pattern: str
    category: str
    priority: int = 100                         # lower number = evaluated first
    created_at: str = ""


class Bill(BaseModel):
    id: str
    side: str
    account_id: str
    name: str
    due_date: str                               # ISO date
    amount_due_cents: int = 0
    minimum_payment_cents: int = 0
    paid: bool = False
    created_at: str = ""


# --- Request payloads (FastAPI) --------------------------------------------

class AccountCreate(BaseModel):
    institution: str
    name: str
    account_type: str = "checking"
    external_id: str = ""
    credit_limit_cents: int = 0
    balance_cents: int = 0
    currency: str = "USD"


class TransactionCreate(BaseModel):
    account_id: str
    posted_date: str
    amount_cents: int
    description: str = ""
    category: Optional[str] = None
    dedup_key: str = ""
    provider: str = "manual"


class RuleCreate(BaseModel):
    match_type: str = "contains"
    pattern: str
    category: str
    priority: int = 100


class BillCreate(BaseModel):
    account_id: str
    name: str
    due_date: str
    amount_due_cents: int = 0
    minimum_payment_cents: int = 0


class IngestRequest(BaseModel):
    provider: Optional[str] = None              # csv | mock | simplefin
    csv_path: Optional[str] = None
    dry_run: bool = False
