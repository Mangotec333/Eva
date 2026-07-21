"""
Offline test suite for the Storeys investor-outreach sourcing pipeline.

Mirrors ``test_apollo.py``'s structure exactly, but exercises the Storeys-only
modules (storeys_investor_gate/store/ledger) so Eva Acquisition's tables and
ledger are never touched by this test run.

Zero network: Apollo is mocked via an injected search fn, GHL uses the
offline StubGHLClient, Slack no-ops (no SLACK_BOT_TOKEN), and the dedup
ledger is forced onto a throwaway SQLite file.

Runs under pytest *or* standalone:  python3 test_storeys_investor.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="storeys_investor_test_")
os.environ["STOREYS_INVESTOR_LEDGER_DB"] = os.path.join(_TMP, "enrolled.db")
os.environ["STOREYS_INVESTOR_STORE_DB"] = os.path.join(_TMP, "batches.db")
os.environ["EVA_GHL_OFFLINE"] = "1"
os.environ.pop("SLACK_BOT_TOKEN", None)
os.environ.pop("APOLLO_API_KEY", None)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GHL = os.path.abspath(os.path.join(_HERE, "..", "ghl-agent"))
for p in (_HERE, _GHL):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_client
import storeys_investor_gate as gate
import storeys_investor_ledger as ledger
import storeys_investor_store as store


# --- Mock Apollo payload ----------------------------------------------------

def _mock_people(n: int) -> list[dict]:
    return [
        {
            "first_name": f"Investor{i}",
            "last_name": f"Family{i}",
            "title": "Managing Partner",
            "email": f"investor{i}@familyoffice.com",
            "organization": {"name": f"Family Office {i}"},
        }
        for i in range(n)
    ]


def _mock_search(query="", *, page=1, per_page=100, **kw) -> dict:
    all_people = _mock_people(5)
    start = (page - 1) * per_page
    chunk = all_people[start:start + per_page]
    return {"ok": True, "people": chunk, "pagination": {"page": page, "total_pages": 1}}


def _stub_ghl_with_pipeline():
    stub = ghl_client.StubGHLClient()
    stub.create_pipeline(gate.PIPELINE_NAME, ["New Lead", "Contacted"])
    gate._ghl_client = lambda: stub
    return stub


def _wipe_ledger():
    import sqlite3
    with sqlite3.connect(os.environ["STOREYS_INVESTOR_LEDGER_DB"]) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS storeys_investor_enrolled "
                     "(email TEXT PRIMARY KEY, source TEXT, ghl_contact_id TEXT, enrolled_at TEXT)")
        conn.execute("DELETE FROM storeys_investor_enrolled")
        conn.commit()


# --- Tests ------------------------------------------------------------------

def test_extract_uses_storeys_icp_not_default_titles():
    # gate.extract_and_stage must pass Storeys titles/keywords, not apollo_connector's
    # Eva-Acquisition (PE/M&A) defaults.
    _wipe_ledger()  # order-independent: start from an empty ledger
    seen = {}

    def spy_search(query, page=1, per_page=100, titles=None, firm_keywords=None,
                   locations=None, timeout=30.0):
        seen["titles"] = titles
        seen["firm_keywords"] = firm_keywords
        return _mock_search(query, page=page, per_page=per_page)

    res = gate.extract_and_stage("", max_contacts=5, _search_fn=spy_search)
    assert res["ok"] is True
    assert seen["titles"] == gate.DEFAULT_TITLES
    assert "Family Office" in seen["firm_keywords"]
    assert res["staged"] == 5
    print("PASS test_extract_uses_storeys_icp_not_default_titles")


def test_dedup_skips_enrolled():
    _wipe_ledger()
    ledger.mark_enrolled("investor0@familyoffice.com", "apollo-re-investor", "c_existing")
    assert ledger.is_enrolled("INVESTOR0@FAMILYOFFICE.COM") is True  # case-insensitive
    staged = gate.extract_and_stage("", max_contacts=5, _search_fn=_mock_search)
    assert staged["ok"] is True
    assert staged["deduped_out"] == 1
    assert staged["staged"] == 4
    emails = [c["email"] for c in staged["batch"]["contacts"]]
    assert "investor0@familyoffice.com" not in emails
    print("PASS test_dedup_skips_enrolled")


def test_enroll_refuses_pre_approval():
    _wipe_ledger()
    staged = gate.extract_and_stage("", max_contacts=3, _search_fn=_mock_search)
    batch = staged["batch"]
    assert batch["status"] == store.STATUS_PENDING
    refused = gate.enroll(batch)
    assert refused["ok"] is False
    assert "refusing to enrol" in refused["error"]
    print("PASS test_enroll_refuses_pre_approval")


def test_approve_files_into_storeys_pipeline_not_workflow():
    _wipe_ledger()
    stub = _stub_ghl_with_pipeline()
    staged = gate.extract_and_stage("", max_contacts=3, _search_fn=_mock_search)
    batch_id = staged["batch"]["id"]
    out = gate.approve(batch_id, actor="test", via="endpoint")
    assert out["ok"] is True
    results = out["results"]
    assert results["success"] == 3
    assert results["pipeline_error"] == ""
    # Every enrolled contact must be filed as an opportunity in the resolved
    # Storeys pipeline/stage — no workflow-trigger tag (Storeys has none yet).
    assert len(stub.opportunities) == 3
    pipe = stub.pipelines[0]
    stage_id = next(s["id"] for s in pipe["stages"] if s["name"] == "New Lead")
    for o in stub.opportunities:
        assert o["pipeline_id"] == pipe["id"]
        assert o["stage_id"] == stage_id
    for c in stub.contacts.values():
        assert gate.LEAD_TAG in c["tags"]
        assert gate.SOURCE_TAG in c["tags"]
    # Idempotent re-approve.
    again = gate.approve(batch_id)
    assert again.get("noop") is True
    for c in staged["batch"]["contacts"]:
        assert ledger.is_enrolled(c["email"]) is True
    print("PASS test_approve_files_into_storeys_pipeline_not_workflow")


def test_enroll_reports_missing_pipeline_without_crashing():
    _wipe_ledger()
    stub = ghl_client.StubGHLClient()  # no pipeline created
    gate._ghl_client = lambda: stub
    staged = gate.extract_and_stage("", max_contacts=2, _search_fn=_mock_search)
    out = gate.approve(staged["batch"]["id"], actor="test")
    assert out["ok"] is True
    assert "pipeline 'Storeys Investor Outreach' not found" in out["results"]["pipeline_error"]
    # Contacts are still upserted + ledgered even if the pipeline can't be resolved.
    assert out["results"]["success"] == 2
    assert len(stub.opportunities) == 0
    print("PASS test_enroll_reports_missing_pipeline_without_crashing")


def test_eva_acquisition_ledger_untouched():
    # Storeys enrolment must never write to the Eva Acquisition ledger/tables.
    import enrolled_contacts
    os.environ["EVA_ENROLLED_OFFLINE"] = "1"
    before = enrolled_contacts.count()
    _wipe_ledger()
    stub = _stub_ghl_with_pipeline()
    staged = gate.extract_and_stage("", max_contacts=2, _search_fn=_mock_search)
    gate.approve(staged["batch"]["id"], actor="test")
    after = enrolled_contacts.count()
    assert after == before, "Storeys enrolment must not write to the Eva Acquisition ledger"
    print("PASS test_eva_acquisition_ledger_untouched")


def test_launcher_routes_registered():
    import importlib
    launcher_dir = os.path.abspath(os.path.join(_HERE, "..", "launcher"))
    if launcher_dir not in sys.path:
        sys.path.insert(0, launcher_dir)
    mod = importlib.import_module("eva_launcher")
    paths = {r.path for r in mod.app.routes}
    expected = {
        "/storeys/apollo/extract", "/storeys/apollo/batch/{batch_id}",
        "/storeys/apollo/enroll/{batch_id}", "/storeys/apollo/reject/{batch_id}",
        "/storeys/apollo/check-approvals", "/storeys/apollo/creds",
        # Eva Acquisition routes must still be present, untouched.
        "/apollo/search", "/apollo/extract", "/apollo/batch/{batch_id}",
        "/apollo/enroll/{batch_id}", "/apollo/creds",
    }
    missing = expected - paths
    assert not missing, f"missing launcher routes: {missing}"
    print("PASS test_launcher_routes_registered (11/11)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
