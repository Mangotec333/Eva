"""
EVA Treasurer — provider-abstracted ingestion layer.

Mirrors the "swap-and-play" seam used elsewhere in EVA (see
``modules/monetizing-agent/brain.py`` and the shared ``BrainClient`` /
``ResearchClient`` transports): agent/ingestion logic depends only on the
``IngestionProvider`` Protocol, never on a concrete provider. A concrete
provider is chosen at the edge by the env-driven ``make_provider`` factory.

Providers return a normalized ``IngestResult`` — a plain dict of accounts +
transactions in Treasurer's own shape — so the store never learns anything
about the upstream data format.

Implementations
---------------
* ``CSVProvider``      — reads a local CSV. Works today, zero external deps.
* ``MockProvider``     — returns fixture data. Used by the test-suite and demos.
* ``SimpleFINProvider``— pulls accounts/balances/transactions from a SimpleFIN
  Bridge over HTTP (``SIMPLEFIN_BRIDGE_URL``). Fully wired, but since no live
  token is available it is exercised only through an injected ``http_get`` so
  tests can feed it a fixture with no network.

Normalized ``IngestResult`` shape::

    {
      "provider": str,
      "accounts": [
        {external_id, institution, name, account_type,
         credit_limit_cents, balance_cents, currency}
      ],
      "transactions": [
        {account_external_id, posted_date, amount_cents,
         description, category?, dedup_key?}
      ],
    }
"""

from __future__ import annotations

import csv
import os
from typing import Any, Callable, Optional, Protocol, runtime_checkable

IngestResult = dict[str, Any]


@runtime_checkable
class IngestionProvider(Protocol):
    """Swap-and-play seam: produce a normalized ``IngestResult`` for one side."""

    name: str

    def fetch(self, side: str) -> IngestResult:
        ...


def _empty_result(provider: str) -> IngestResult:
    return {"provider": provider, "accounts": [], "transactions": []}


def _to_cents(value: Any) -> int:
    """Parse a dollar amount (str/float/int) into signed integer cents."""
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "").replace("$", "")
    return int(round(float(text) * 100))


# ---------------------------------------------------------------------------
# CSV / manual import
# ---------------------------------------------------------------------------

class CSVProvider:
    """Import transactions from a local CSV file. No external dependency.

    Expected columns (header row, case-insensitive):
        institution, account, account_type, date, amount, description
        [, category, credit_limit, balance, external_id]

    ``amount`` is in dollars (e.g. ``-42.50``); negative = spend. Each distinct
    (institution, account) pair becomes/updates one account.
    """

    name = "csv"

    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def fetch(self, side: str) -> IngestResult:
        result = _empty_result(self.name)
        seen_accounts: dict[tuple[str, str], dict] = {}
        with open(self.csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in raw.items()}
                institution = row.get("institution", "")
                account_name = row.get("account", "")
                key = (institution, account_name)
                if key not in seen_accounts:
                    acct = {
                        "external_id": row.get("external_id", "")
                        or f"csv:{institution}:{account_name}",
                        "institution": institution,
                        "name": account_name,
                        "account_type": row.get("account_type", "checking") or "checking",
                        "credit_limit_cents": _to_cents(row.get("credit_limit", 0)),
                        "balance_cents": _to_cents(row.get("balance", 0)),
                        "currency": row.get("currency", "USD") or "USD",
                    }
                    seen_accounts[key] = acct
                    result["accounts"].append(acct)
                result["transactions"].append({
                    "account_external_id": seen_accounts[key]["external_id"],
                    "posted_date": row.get("date", ""),
                    "amount_cents": _to_cents(row.get("amount", 0)),
                    "description": row.get("description", ""),
                    "category": row.get("category") or None,
                    "dedup_key": row.get("dedup_key", ""),
                })
        return result


# ---------------------------------------------------------------------------
# Mock (fixture-backed)
# ---------------------------------------------------------------------------

class MockProvider:
    """Return a fixed ``IngestResult`` from an in-memory fixture dict.

    Personal and business fixtures are keyed by side so tests can prove the two
    sides ingest disjoint data.
    """

    name = "mock"

    def __init__(self, fixture_by_side: Optional[dict[str, IngestResult]] = None):
        self._fixture = fixture_by_side or _default_fixture()

    def fetch(self, side: str) -> IngestResult:
        data = self._fixture.get(side)
        if data is None:
            return _empty_result(self.name)
        # Return a shallow copy so callers can't mutate the fixture.
        return {
            "provider": self.name,
            "accounts": [dict(a) for a in data.get("accounts", [])],
            "transactions": [dict(t) for t in data.get("transactions", [])],
        }


def _default_fixture() -> dict[str, IngestResult]:
    return {
        "personal": {
            "provider": "mock",
            "accounts": [
                {"external_id": "p-chk-1", "institution": "Chase", "name": "Personal Checking",
                 "account_type": "checking", "credit_limit_cents": 0,
                 "balance_cents": 250000, "currency": "USD"},
                {"external_id": "p-cc-1", "institution": "Amex", "name": "Personal Gold",
                 "account_type": "credit_card", "credit_limit_cents": 1000000,
                 "balance_cents": 420000, "currency": "USD"},
            ],
            "transactions": [
                {"account_external_id": "p-chk-1", "posted_date": "2026-07-01",
                 "amount_cents": 500000, "description": "Payroll deposit", "category": "income"},
                {"account_external_id": "p-chk-1", "posted_date": "2026-07-03",
                 "amount_cents": -8500, "description": "Whole Foods Market"},
                {"account_external_id": "p-cc-1", "posted_date": "2026-07-05",
                 "amount_cents": -12000, "description": "Shell Gas Station"},
            ],
        },
        "business": {
            "provider": "mock",
            "accounts": [
                {"external_id": "b-chk-1", "institution": "Mercury", "name": "Mangotec Operating",
                 "account_type": "checking", "credit_limit_cents": 0,
                 "balance_cents": 1500000, "currency": "USD"},
                {"external_id": "b-cc-1", "institution": "Chase Ink", "name": "Business Card",
                 "account_type": "credit_card", "credit_limit_cents": 2000000,
                 "balance_cents": 300000, "currency": "USD"},
            ],
            "transactions": [
                {"account_external_id": "b-chk-1", "posted_date": "2026-07-02",
                 "amount_cents": 1200000, "description": "Client invoice #1042", "category": "income"},
                {"account_external_id": "b-chk-1", "posted_date": "2026-07-04",
                 "amount_cents": -45000, "description": "AWS"},
                {"account_external_id": "b-cc-1", "posted_date": "2026-07-06",
                 "amount_cents": -9900, "description": "Anthropic API"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# SimpleFIN Bridge (real provider — HTTP layer is injectable for tests)
# ---------------------------------------------------------------------------

class SimpleFINProvider:
    """Pull accounts/balances/transactions from a SimpleFIN Bridge.

    Configured via ``SIMPLEFIN_BRIDGE_URL`` — the "access URL" the Bridge issues
    after a token claim. It already contains basic-auth credentials, e.g.
    ``https://user:pass@bridge.simplefin.org/simplefin``. This provider GETs
    ``<url>/accounts`` and maps the SimpleFIN JSON schema into Treasurer's shape.

    No live token is available in this environment, so the HTTP call is made
    through the injectable ``http_get`` (defaults to ``requests.get``). Tests
    pass a fake ``http_get`` that returns a fixture — no network is touched.

    SimpleFIN amounts are decimal-dollar strings and its ``org`` block carries
    the institution name; transaction ``id`` is a stable dedup key.
    """

    name = "simplefin"

    def __init__(self, bridge_url: Optional[str] = None,
                 http_get: Optional[Callable[..., Any]] = None):
        self.bridge_url = (bridge_url or os.environ.get("SIMPLEFIN_BRIDGE_URL", "")).rstrip("/")
        self._http_get = http_get

    def _get(self, url: str) -> dict:
        getter = self._http_get
        if getter is None:  # lazy import so tests never require `requests`
            import requests
            getter = requests.get
        resp = getter(url, timeout=30)
        # Support both requests.Response and simple fakes exposing .json().
        return resp.json()

    def fetch(self, side: str) -> IngestResult:
        result = _empty_result(self.name)
        if not self.bridge_url:
            raise ValueError(
                "SIMPLEFIN_BRIDGE_URL is not configured — cannot pull from SimpleFIN"
            )
        payload = self._get(f"{self.bridge_url}/accounts")
        for acct in payload.get("accounts", []):
            org = acct.get("org", {}) or {}
            institution = org.get("name") or org.get("domain") or "SimpleFIN"
            account_type = self._infer_type(acct)
            credit_limit_cents = _to_cents(
                acct.get("available-balance-limit")
                or acct.get("credit-limit")
                or 0
            )
            result["accounts"].append({
                "external_id": acct.get("id", ""),
                "institution": institution,
                "name": acct.get("name", acct.get("id", "")),
                "account_type": account_type,
                "credit_limit_cents": credit_limit_cents,
                "balance_cents": _to_cents(acct.get("balance", 0)),
                "currency": acct.get("currency", "USD"),
            })
            for txn in acct.get("transactions", []):
                result["transactions"].append({
                    "account_external_id": acct.get("id", ""),
                    "posted_date": self._posted_date(txn),
                    "amount_cents": _to_cents(txn.get("amount", 0)),
                    "description": txn.get("description", ""),
                    "category": None,
                    "dedup_key": txn.get("id", ""),
                })
        return result

    @staticmethod
    def _infer_type(acct: dict) -> str:
        """SimpleFIN has no explicit type; a positive credit limit implies a card."""
        if _to_cents(acct.get("available-balance-limit") or acct.get("credit-limit") or 0) > 0:
            return "credit_card"
        return "checking"

    @staticmethod
    def _posted_date(txn: dict) -> str:
        """SimpleFIN 'posted' is a unix epoch (seconds). Fall back to raw string."""
        posted = txn.get("posted")
        if isinstance(posted, (int, float)):
            from datetime import datetime, timezone
            return datetime.fromtimestamp(posted, tz=timezone.utc).date().isoformat()
        return str(posted or "")


# ---------------------------------------------------------------------------
# Env-driven factory
# ---------------------------------------------------------------------------

def make_provider(name: Optional[str] = None, *, csv_path: Optional[str] = None,
                  http_get: Optional[Callable[..., Any]] = None,
                  fixture_by_side: Optional[dict[str, IngestResult]] = None) -> IngestionProvider:
    """Return an ``IngestionProvider`` chosen by ``name`` or ``TREASURER_PROVIDER``.

    Recognized names: ``csv``, ``mock``, ``simplefin`` (default ``mock`` — the
    only provider guaranteed to work offline with zero configuration).
    """
    name = (name or os.environ.get("TREASURER_PROVIDER", "mock")).lower()

    if name == "csv":
        path = csv_path or os.environ.get("TREASURER_CSV_PATH", "")
        if not path:
            raise ValueError("csv provider requires csv_path (or TREASURER_CSV_PATH)")
        return CSVProvider(path)
    if name == "simplefin":
        return SimpleFINProvider(http_get=http_get)
    if name == "mock":
        return MockProvider(fixture_by_side=fixture_by_side)
    raise ValueError(f"unknown provider {name!r}; expected csv|mock|simplefin")
