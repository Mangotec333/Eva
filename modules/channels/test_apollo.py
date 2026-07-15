"""
Offline test suite for the Apollo → GHL cold-outreach pipeline.

Zero network: Apollo is mocked via an injected search fn, GHL uses the offline
StubGHLClient (no GHL_ACCESS_TOKEN), Slack no-ops (no SLACK_BOT_TOKEN), and the
dedup ledger is forced onto its SQLite fallback.

Runs under pytest *or* standalone:  python3 test_apollo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

# Isolate every persistent store into a throwaway dir + force offline backends
# BEFORE importing the modules that read these at import time.
_TMP = tempfile.mkdtemp(prefix="apollo_test_")
os.environ["EVA_ENROLLED_OFFLINE"] = "1"
os.environ["ENROLLED_CONTACTS_DB"] = os.path.join(_TMP, "enrolled.db")
os.environ["APOLLO_STORE_DB"] = os.path.join(_TMP, "batches.db")
os.environ["EVA_GHL_OFFLINE"] = "1"
os.environ.pop("SLACK_BOT_TOKEN", None)
os.environ.pop("APOLLO_API_KEY", None)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GHL = os.path.abspath(os.path.join(_HERE, "..", "ghl-agent"))
for p in (_HERE, _GHL):
    if p not in sys.path:
        sys.path.insert(0, p)

import apollo_connector
import apollo_gate
import apollo_store
import enrolled_contacts
import campaign


# --- Mock Apollo payload ----------------------------------------------------

def _mock_people(n: int) -> list[dict]:
    return [
        {
            "first_name": f"First{i}",
            "last_name": f"Last{i}",
            "title": "Managing Director",
            "email": f"person{i}@pefirm.com",
            "linkedin_url": f"https://linkedin.com/in/person{i}",
            "organization": {"name": f"PE Firm {i}"},
            "phone_numbers": [{"sanitized_number": f"+1202555{i:04d}"}],
        }
        for i in range(n)
    ]


def _mock_search(query="", *, page=1, per_page=100, **kw) -> dict:
    # Two pages of 60 → 120 available; extract should cap at 100.
    all_people = _mock_people(120)
    start = (page - 1) * per_page
    chunk = all_people[start:start + per_page]
    total_pages = 2
    return {"ok": True, "people": chunk,
            "pagination": {"page": page, "total_pages": total_pages}}


# --- Tests ------------------------------------------------------------------

def test_extract_normalizes_and_caps():
    res = apollo_connector.extract_contacts("", max_contacts=100, _search_fn=_mock_search)
    assert res["ok"] is True
    assert len(res["contacts"]) == 100, "first batch must cap at 100"
    c = res["contacts"][0]
    assert set(["name", "email", "title", "company", "linkedin_url", "phone"]).issubset(c)
    assert c["name"] == "First0 Last0"
    assert c["company"] == "PE Firm 0"
    assert c["phone"] == "+12025550000"
    print("PASS test_extract_normalizes_and_caps")


def test_locked_emails_filtered():
    locked = [{"name": "Locked One", "email": "email_not_unlocked@domain.com",
               "title": "Partner", "organization": {"name": "X"}}]
    res = apollo_connector.extract_contacts(
        "", _search_fn=lambda *a, **k: {"ok": True, "people": locked, "pagination": {"total_pages": 1}})
    assert res["contacts"] == [], "locked/un-revealed emails must be filtered"
    print("PASS test_locked_emails_filtered")


def test_search_missing_key_fails_safe():
    res = apollo_connector.search_people("test")
    assert res["ok"] is False and "APOLLO_API_KEY" in res["error"]
    print("PASS test_search_missing_key_fails_safe")


def _wipe_enrolled():
    import sqlite3
    with sqlite3.connect(os.environ["ENROLLED_CONTACTS_DB"]) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS enrolled_contacts "
                     "(email TEXT UNIQUE, source TEXT, ghl_contact_id TEXT, enrolled_at TEXT)")
        conn.execute("DELETE FROM enrolled_contacts")
        conn.commit()


def test_dedup_skips_enrolled():
    _wipe_enrolled()  # order-independent: start from an empty ledger
    enrolled_contacts.mark_enrolled("person0@pefirm.com", "apollo-pe-ma", "c_existing")
    assert enrolled_contacts.is_enrolled("PERSON0@PEFIRM.COM") is True  # case-insensitive
    staged = apollo_gate.extract_and_stage("", max_contacts=100, _search_fn=_mock_search)
    assert staged["ok"] is True
    assert staged["deduped_out"] == 1, "already-enrolled email must be deduped out"
    assert staged["staged"] == 99
    emails = [c["email"] for c in staged["batch"]["contacts"]]
    assert "person0@pefirm.com" not in emails
    print("PASS test_dedup_skips_enrolled")


def test_enroll_refuses_pre_approval():
    staged = apollo_gate.extract_and_stage("", max_contacts=5, _search_fn=_mock_search)
    batch = staged["batch"]
    assert batch["status"] == apollo_store.STATUS_PENDING
    # Directly attempting to enrol a non-approved batch must be refused.
    refused = apollo_gate.enroll(batch)
    assert refused["ok"] is False
    assert "refusing to enrol" in refused["error"]
    print("PASS test_enroll_refuses_pre_approval")


def test_approve_then_enroll_fires_trigger():
    staged = apollo_gate.extract_and_stage("", max_contacts=5, _search_fn=_mock_search)
    batch_id = staged["batch"]["id"]
    out = apollo_gate.approve(batch_id, actor="test", via="endpoint")
    assert out["ok"] is True
    results = out["results"]
    assert results["success"] >= 1
    # Re-running approve is a no-op (idempotent) and everyone is now enrolled.
    again = apollo_gate.approve(batch_id)
    assert again.get("noop") is True
    for c in staged["batch"]["contacts"]:
        assert enrolled_contacts.is_enrolled(c["email"]) is True
    print("PASS test_approve_then_enroll_fires_trigger")


def test_magnet_block_in_render_touches():
    block = campaign.magnet_block()
    for _, url in campaign.MAGNETS:
        assert url in block
    rendered = campaign.render_touches("https://book.me/eva")
    email_bodies = [t["body"] for t in rendered if t["channel"] == "email"]
    assert email_bodies, "expected email touches"
    for body in email_bodies:
        assert "Free resources:" in body
        assert "https://eva-acquisition.mangotec.ai/whitepaper" in body
    # Validation still passes (no banned words introduced by the magnets).
    assert campaign.validate_touches()["ok"] is True
    print("PASS test_magnet_block_in_render_touches")


def test_launcher_routes_registered():
    import importlib
    launcher_dir = os.path.abspath(os.path.join(_HERE, "..", "launcher"))
    if launcher_dir not in sys.path:
        sys.path.insert(0, launcher_dir)
    mod = importlib.import_module("eva_launcher")
    paths = {r.path for r in mod.app.routes}
    expected = {
        "/apollo/search", "/apollo/extract", "/apollo/batch/{batch_id}",
        "/apollo/enroll/{batch_id}", "/apollo/creds",
    }
    missing = expected - paths
    assert not missing, f"missing launcher routes: {missing}"
    print("PASS test_launcher_routes_registered (5/5)")


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
