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


def _write_map(tmp_path, mapping):
    """Write an account->side map JSON and return its path."""
    path = os.path.join(str(tmp_path), "account_sides.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh)
    return path


def test_simplefin_provider_maps_fixture(fixtures_dir):
    """fetch_all() returns every linked account, normalized (no side filter)."""
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, calls = _fake_http_get_factory(payload)
    prov = SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                             http_get=get)
    result = prov.fetch_all()

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


def test_simplefin_fetch_filters_by_side(fixtures_dir, tmp_path):
    """With a map, fetch(side) yields disjoint account sets per side."""
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    map_path = _write_map(tmp_path, {"personal": ["sfin-chk-001"],
                                     "business": ["sfin-cc-001"]})

    def _prov():
        get, _ = _fake_http_get_factory(payload)
        return SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                                 http_get=get, map_path=map_path)

    personal = _prov().fetch("personal")
    business = _prov().fetch("business")

    p_ids = {a["external_id"] for a in personal["accounts"]}
    b_ids = {a["external_id"] for a in business["accounts"]}
    assert p_ids == {"sfin-chk-001"}
    assert b_ids == {"sfin-cc-001"}
    assert p_ids.isdisjoint(b_ids)
    # Transactions follow their account, so they are disjoint too.
    p_txn_accts = {t["account_external_id"] for t in personal["transactions"]}
    b_txn_accts = {t["account_external_id"] for t in business["transactions"]}
    assert p_txn_accts == {"sfin-chk-001"}
    assert b_txn_accts == {"sfin-cc-001"}


def test_simplefin_fetch_missing_map_raises(fixtures_dir, tmp_path):
    """A missing map is a hard error — never a silent 'ingest everything'."""
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, _ = _fake_http_get_factory(payload)
    missing = os.path.join(str(tmp_path), "does_not_exist.json")
    prov = SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                             http_get=get, map_path=missing)
    with pytest.raises(ValueError, match="account map not found"):
        prov.fetch("personal")


def test_simplefin_map_duplicate_side_raises(tmp_path):
    """An id assigned to both sides is ambiguous and rejected at load time."""
    from providers import load_account_map
    map_path = _write_map(tmp_path, {"personal": ["sfin-chk-001", "dup-id"],
                                     "business": ["dup-id"]})
    with pytest.raises(ValueError, match="both"):
        load_account_map(map_path)


def test_simplefin_ingestion_end_to_end(personal_store, fixtures_dir, tmp_path):
    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, _ = _fake_http_get_factory(payload)
    map_path = _write_map(tmp_path, {"personal": ["sfin-chk-001", "sfin-cc-001"],
                                     "business": []})
    prov = SimpleFINProvider(bridge_url="https://u:p@bridge.example/simplefin",
                             http_get=get, map_path=map_path)
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
        prov.fetch_all()


def test_accounts_cli_returns_unfiltered_raw(fixtures_dir, monkeypatch):
    """`accounts --provider simplefin` lists every linked account (no side)."""
    import cli
    import providers

    with open(os.path.join(fixtures_dir, "simplefin_accounts.json")) as fh:
        payload = json.load(fh)
    get, _ = _fake_http_get_factory(payload)

    # Force SimpleFINProvider() (constructed inside the CLI) to use our fake HTTP.
    real_init = providers.SimpleFINProvider.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs.setdefault("bridge_url", "https://u:p@bridge.example/simplefin")
        kwargs.setdefault("http_get", get)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(providers.SimpleFINProvider, "__init__", _patched_init)

    raw = cli._list_raw_accounts("simplefin")
    ids = {a["external_id"] for a in raw}
    assert ids == {"sfin-chk-001", "sfin-cc-001"}
    # Inspection payload is metadata only — no balances/transactions leak in.
    assert all(set(a) == {"external_id", "institution", "name", "account_type"}
               for a in raw)


def _patch_simplefin_http(monkeypatch, payload):
    """Force every SimpleFINProvider() built inside the CLI to use fake HTTP."""
    import providers
    get, _ = _fake_http_get_factory(payload)
    real_init = providers.SimpleFINProvider.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs.setdefault("bridge_url", "https://u:p@bridge.example/simplefin")
        kwargs.setdefault("http_get", get)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(providers.SimpleFINProvider, "__init__", _patched_init)


def test_suggest_sides_classifies_and_writes(tmp_path, monkeypatch):
    """--suggest-sides classifies by name and emits a loader-compatible file."""
    import cli
    from providers import load_account_map

    payload = {"accounts": [
        {"org": {"name": "Chase Ink Business"}, "id": "b-1", "name": "Ink Card",
         "balance": "0", "available-balance-limit": "5000.00", "transactions": []},
        {"org": {"name": "Chase"}, "id": "p-1", "name": "Personal Checking",
         "balance": "100.00", "transactions": []},
    ]}
    _patch_simplefin_http(monkeypatch, payload)
    map_path = os.path.join(str(tmp_path), "account_sides.json")
    monkeypatch.setenv("TREASURER_ACCOUNT_MAP_PATH", map_path)

    mapping = cli._suggest_sides("simplefin")
    assert mapping == {"personal": ["p-1"], "business": ["b-1"]}
    # File was written and round-trips through the real loader unchanged.
    assert load_account_map(map_path) == {"personal": ["p-1"], "business": ["b-1"]}


def test_suggest_sides_refuses_existing_file(tmp_path, monkeypatch):
    """A pre-existing account_sides.json is never silently overwritten."""
    import cli

    payload = {"accounts": [
        {"org": {"name": "Chase"}, "id": "p-1", "name": "Checking",
         "balance": "1.00", "transactions": []},
    ]}
    _patch_simplefin_http(monkeypatch, payload)
    map_path = os.path.join(str(tmp_path), "account_sides.json")
    with open(map_path, "w", encoding="utf-8") as fh:
        fh.write('{"personal": ["hand-edited"], "business": []}')
    monkeypatch.setenv("TREASURER_ACCOUNT_MAP_PATH", map_path)

    with pytest.raises(ValueError, match="already exists"):
        cli._suggest_sides("simplefin")
    # Existing hand-edited file left untouched.
    with open(map_path, encoding="utf-8") as fh:
        assert json.load(fh) == {"personal": ["hand-edited"], "business": []}


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
