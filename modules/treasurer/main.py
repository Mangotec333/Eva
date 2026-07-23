"""
EVA Treasurer — FastAPI service (port 8794).

Provider-abstracted personal/business finance module. Every endpoint that
touches ledger data is scoped to one ``side`` ("personal" | "business"); the
two sides live in separate SQLite databases and are never joined. The
``/summary`` endpoint returns the two sides as separate, clearly-labeled
sections, ready for a Command Center dashboard tile.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from models import (
    VALID_SIDES,
    AccountCreate,
    BillCreate,
    IngestRequest,
    RuleCreate,
    TransactionCreate,
)
import bills as bills_engine
import budgeting
from categorize import apply_rules_to_store, categorize
from ingest import run_ingestion
from store import open_side

app = FastAPI(title="EVA Treasurer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_side(side: str) -> str:
    if side not in VALID_SIDES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid side {side!r}; must be one of {VALID_SIDES}",
        )
    return side


def _open(side: str):
    return open_side(_require_side(side))


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "module": "eva-treasurer", "version": "1.0.0", "port": 8794}


# ── Accounts ──────────────────────────────────────────────────────────────────

@app.get("/{side}/accounts")
def list_accounts(side: str = Path(...)):
    store = _open(side)
    try:
        return {"side": side, "accounts": store.list_accounts()}
    finally:
        store.close()


@app.post("/{side}/accounts", status_code=201)
def create_account(body: AccountCreate, side: str = Path(...)):
    store = _open(side)
    try:
        acct = store.upsert_account(
            institution=body.institution, name=body.name,
            account_type=body.account_type, external_id=body.external_id,
            credit_limit_cents=body.credit_limit_cents,
            balance_cents=body.balance_cents, currency=body.currency,
        )
        return {"side": side, "account": acct}
    finally:
        store.close()


# ── Transactions ────────────────────────────────────────────────────────────

@app.get("/{side}/transactions")
def list_transactions(side: str = Path(...),
                      account_id: str = Query(None),
                      start: str = Query(None), end: str = Query(None)):
    store = _open(side)
    try:
        return {
            "side": side,
            "transactions": store.list_transactions(
                account_id=account_id, start=start, end=end),
        }
    finally:
        store.close()


@app.post("/{side}/transactions", status_code=201)
def create_transaction(body: TransactionCreate, side: str = Path(...)):
    store = _open(side)
    try:
        category = body.category
        if not category:
            category = categorize(body.description, store.list_rules()) or "uncategorized"
        res = store.add_transaction(
            account_id=body.account_id, posted_date=body.posted_date,
            amount_cents=body.amount_cents, description=body.description,
            category=category, dedup_key=body.dedup_key, provider=body.provider,
        )
        return {"side": side, **res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.close()


# ── Categorization rules ─────────────────────────────────────────────────────

@app.get("/{side}/rules")
def list_rules(side: str = Path(...)):
    store = _open(side)
    try:
        return {"side": side, "rules": store.list_rules()}
    finally:
        store.close()


@app.post("/{side}/rules", status_code=201)
def create_rule(body: RuleCreate, side: str = Path(...)):
    store = _open(side)
    try:
        rule = store.add_rule(match_type=body.match_type, pattern=body.pattern,
                              category=body.category, priority=body.priority)
        return {"side": side, "rule": rule}
    finally:
        store.close()


@app.post("/{side}/recategorize")
def recategorize(side: str = Path(...)):
    store = _open(side)
    try:
        updated = apply_rules_to_store(store)
        return {"side": side, "updated": updated}
    finally:
        store.close()


# ── Bills ──────────────────────────────────────────────────────────────────

@app.get("/{side}/bills")
def list_bills(side: str = Path(...), within_days: int = Query(30)):
    store = _open(side)
    try:
        return {"side": side, "bills": bills_engine.upcoming_bills(store, within_days)}
    finally:
        store.close()


@app.post("/{side}/bills", status_code=201)
def create_bill(body: BillCreate, side: str = Path(...)):
    store = _open(side)
    try:
        bill = store.add_bill(
            account_id=body.account_id, name=body.name, due_date=body.due_date,
            amount_due_cents=body.amount_due_cents,
            minimum_payment_cents=body.minimum_payment_cents,
        )
        return {"side": side, "bill": bill}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.close()


# ── Utilization / credit-score protection ───────────────────────────────────

@app.get("/{side}/utilization")
def utilization(side: str = Path(...), threshold: float = Query(0.30)):
    store = _open(side)
    try:
        return bills_engine.utilization_report(store, threshold=threshold)
    finally:
        store.close()


# ── Budgeting ────────────────────────────────────────────────────────────────

@app.get("/{side}/budget")
def budget(side: str = Path(...), period: str = Query(None)):
    store = _open(side)
    try:
        if period:
            if period not in budgeting.PERIODS:
                raise HTTPException(status_code=400,
                                    detail=f"invalid period; must be {budgeting.PERIODS}")
            return budgeting.rollup(store, period)
        return budgeting.all_rollups(store)
    finally:
        store.close()


# ── Ingestion ────────────────────────────────────────────────────────────────

@app.post("/{side}/ingest")
def ingest(body: IngestRequest, side: str = Path(...)):
    store = _open(side)
    try:
        return run_ingestion(
            store, provider_name=body.provider, csv_path=body.csv_path,
            dry_run=body.dry_run,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.close()


# ── Combined summary (dashboard tile) ────────────────────────────────────────

def _side_summary(side: str, threshold: float) -> dict:
    store = open_side(side)
    try:
        return {
            "side": side,
            "accounts": store.list_accounts(),
            "budget": budgeting.all_rollups(store),
            "upcoming_bills": bills_engine.upcoming_bills(store),
            "utilization": bills_engine.utilization_report(store, threshold=threshold),
        }
    finally:
        store.close()


@app.get("/summary")
def summary(threshold: float = Query(0.30)):
    """Return personal and business as separate, clearly-labeled sections.

    The two sections are computed from separate databases; nothing is merged.
    """
    return {
        "module": "eva-treasurer",
        "separation": "personal and business are stored in separate databases and never merged",
        "personal": _side_summary("personal", threshold),
        "business": _side_summary("business", threshold),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8794, reload=False)
