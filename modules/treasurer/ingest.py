"""
EVA Treasurer — ingestion orchestration.

Takes a normalized ``IngestResult`` from any provider and writes it into one
side's store: upsert accounts (matched by ``external_id``), then insert
transactions with dedup and auto-categorization. Balances from the provider
update the account so utilization stays current.

The store is single-side, so ingestion physically cannot write across the
personal/business boundary.
"""

from __future__ import annotations

from typing import Optional

from categorize import categorize
from providers import IngestionProvider, make_provider


def ingest_result(store, result: dict, *, dry_run: bool = False) -> dict:
    """Write a provider ``IngestResult`` into ``store``. Returns a summary."""
    rules = store.list_rules()
    ext_to_id: dict[str, str] = {}

    accounts_upserted = 0
    for acct in result.get("accounts", []):
        ext = acct.get("external_id", "")
        if dry_run:
            existing = store.find_account_by_external_id(ext)
            if existing:
                ext_to_id[ext] = existing["id"]
            continue
        saved = store.upsert_account(
            institution=acct.get("institution", ""),
            name=acct.get("name", ""),
            account_type=acct.get("account_type", "checking"),
            external_id=ext,
            credit_limit_cents=acct.get("credit_limit_cents", 0),
            balance_cents=acct.get("balance_cents", 0),
            currency=acct.get("currency", "USD"),
        )
        ext_to_id[ext] = saved["id"]
        accounts_upserted += 1

    inserted = 0
    duplicates = 0
    skipped_no_account = 0
    for txn in result.get("transactions", []):
        ext = txn.get("account_external_id", "")
        account_id = ext_to_id.get(ext)
        if account_id is None:
            account_id = _resolve_account(store, ext)
        if account_id is None:
            skipped_no_account += 1
            continue

        category = txn.get("category")
        if not category:
            category = categorize(txn.get("description", ""), rules) or "uncategorized"

        if dry_run:
            inserted += 1
            continue

        res = store.add_transaction(
            account_id=account_id,
            posted_date=txn.get("posted_date", ""),
            amount_cents=txn.get("amount_cents", 0),
            description=txn.get("description", ""),
            category=category,
            dedup_key=txn.get("dedup_key", ""),
            provider=result.get("provider", "manual"),
        )
        if res["inserted"]:
            inserted += 1
        else:
            duplicates += 1

    return {
        "side": store.side,
        "provider": result.get("provider", ""),
        "dry_run": dry_run,
        "accounts_upserted": accounts_upserted,
        "transactions_inserted": inserted,
        "duplicates_skipped": duplicates,
        "transactions_without_account": skipped_no_account,
    }


def _resolve_account(store, external_id: str) -> Optional[str]:
    found = store.find_account_by_external_id(external_id)
    return found["id"] if found else None


def run_ingestion(store, provider: Optional[IngestionProvider] = None, *,
                  provider_name: Optional[str] = None,
                  csv_path: Optional[str] = None,
                  dry_run: bool = False, **factory_kwargs) -> dict:
    """Resolve a provider (or build one via the env-driven factory) and ingest.

    ``store.side`` is passed to ``provider.fetch`` so the provider yields data
    for the correct side.
    """
    if provider is None:
        provider = make_provider(provider_name, csv_path=csv_path, **factory_kwargs)
    result = provider.fetch(store.side)
    return ingest_result(store, result, dry_run=dry_run)
