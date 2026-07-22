"""Provider + ingestion tests: CSV, mock, and a mocked SimpleFIN HTTP layer.

No live network calls: the SimpleFIN provider is driven by an injected
``http_get`` that returns a local fixture.
"""

import json
import os

import pytest

from ingest import ingest_result, run_ingestion
from providers import (
    CSVProvider,
    MockProvider,
    SimpleFINProvider,
    make_provider,
)


# --- CSV --------------------------------------------------------------------

def test_csv_provider_parses_accounts_and_txns(fixtures_dir):
    prov = CSVProvider(os.path.join(fixtures_dir, "personal.csv"))
    result = prov.fetch("personal")
    assert result["provider"] == "csv"
    assert len(result["accounts"]) == 2                # Chase checking + Amex card
    amex = next(a for a in result["accounts"] if a["institution"] == "Amex")
    assert amex["account_type"] == "credit_card"
    assert amex["credit_limit_cents"] == 1000000
    payroll = next(t for t in result["transactions"] if "Payroll" in t["description"])
    assert payroll["amount_cents"] == 500000          # +$5000 dollars -> cents


def test_csv_ingestion_end_to_end(personal_store, fixtures_dir):
    summary = run_ingestion(personal_store, provider_name="csv",
                            csv_path=os.path.join(fixtures_dir, "personal.csv"))
    assert summary["accounts_upserted"] == 2
    assert summary["transactions_inserted"] == 4
    assert summary["side"] == "personal"
    # Auto-categorization ran during ingest.
    cats = {t["description"]: t["category"] for t in personal_store.list_transactions()}
    assert cats["Whole Foods Market"] == "groceries"
    assert cats["Shell Gas Station"] == "fuel"


def test_ingestion_is_idempotent(personal_store, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "personal.csv")
    run_ingestion(personal_store, provider_name="csv", csv_path=csv_path)
    second = run_ingestion(personal_store, provider_name="csv", csv_path=csv_path)
    assert second["transactions_inserted"] == 0
    assert second["duplicates_skipped"] == 4
    assert len(personal_store.list_transactions()) == 4


def test_dry_run_writes_nothing(personal_store, fixtures_dir):
    summary = run_ingestion(personal_store, provider_name="csv",
                            csv_path=os.path.join(fixtures_dir, "personal.csv"),
                            dry_run=True)
    assert summary["dry_run"] is True
    assert personal_store.list_accounts() == []
    assert personal_store.list_transactions() == []


# --- Mock -------------------------------------------------------------------

def test_mock_provider_default_fixture_differs_by_side():
    prov = MockProvider()
    p = prov.fetch("personal")
    b = prov.fetch("business")
    p_insts = {a["institution"] for a in p["accounts"]}
    b_insts = {a["institution"] for a in b["accounts"]}
    assert p_insts == {"Chase", "Amex"}
    assert b_insts == {"Mercury", "Chase Ink"}
    assert p_insts.isdisjoint(b_insts)


def test_mock_ingestion(business_store):
    summary = run_ingestion(business_store, provider_name="mock")
    assert summary["accounts_upserted"] == 2
    assert summary["transactions_inserted"] == 3
    assert summary["side"] == "business"


# --- SimpleFIN (mocked HTTP) ------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_http_get_factory(payload):
    calls = {}

    def _get(url, timeout=None):
        calls["url"] = url
        calls["timeout"] = timeout
        return _FakeResponse(payload)

    return _get, calls


def test_simplefin_provider_maps_fixture(fixtures_dir):
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, calls = _fake_http_get_factory(payload)
    prov = SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                             http_get=get)
    result = prov.fetch("personal")

    assert calls["url"] == "https://u:p@bridge.example/simplefin/accounts"
    assert result["provider"] == "simplefin"
    assert len(result["accounts"]) == 2
    card = next(a for a in result["accounts"] if a["name"] == "Rewards Visa")
    assert card["account_type"] == "credit_card"
    assert card["credit_limit_cents"] == 1000000
    assert card["balance_cents"] == 350000
    # epoch 1751328000 -> 2025-07-01 (UTC)
    payroll = next(t for t in result["transactions"] if "Payroll" in t["description"])
    assert payroll["posted_date"] == "2025-07-01"
    assert payroll["amount_cents"] == 420000
    assert payroll["dedup_key"] == "sfin-txn-1"       # SimpleFIN txn id used for dedup


def test_simplefin_ingestion_end_to_end(personal_store, fixtures_dir):
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, _ = _fake_http_get_factory(payload)
    prov = SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                             http_get=get)
    summary = run_ingestion(personal_store, provider=prov)
    assert summary["accounts_upserted"] == 2
    assert summary["transactions_inserted"] == 3

    report = _utilization(personal_store)
    assert report["alert_count"] == 1                 # 3500/10000 = 35% > 30%


def _utilization(store):
    import bills as bills_engine
    return bills_engine.utilization_report(store)


def test_simplefin_requires_url():
    prov = SimpleFINProvider(bridge_url="", http_get=lambda *a, **k: None)
    with pytest.raises(ValueError):
        prov.fetch("personal")


def test_make_provider_env_and_names(monkeypatch, fixtures_dir):
    assert isinstance(make_provider("mock"), MockProvider)
    assert isinstance(make_provider("csv", csv_path=os.path.join(fixtures_dir, "personal.csv")),
                      CSVProvider)
    assert isinstance(make_provider("simplefin"), SimpleFINProvider)
    with pytest.raises(ValueError):
        make_provider("csv")                          # missing csv_path
    with pytest.raises(ValueError):
        make_provider("bogus")

    monkeypatch.setenv("TREASURER_PROVIDER", "simplefin")
    assert isinstance(make_provider(), SimpleFINProvider)
