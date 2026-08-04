"""Tests for Chad Gardiner's "$5MM+ deal box" — named-box config, the
standalone intake scoring/persistence path, the Gmail sender contract, and the
FastAPI intake/results/GHL-webhook endpoints (network-free).

The endpoint tests stub ``aiosqlite`` (unused by the box flow, but imported at
main-module load for the legacy async DB layer) and drive the app with a
FastAPI ``TestClient`` pointed at a throwaway SQLite file.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest

from box_evaluator import evaluate_box, load_box
from pipeline_models import BoxIntakeResult

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_MODULES = os.path.dirname(MODULE_DIR)

# A deal comfortably above Chad's ~$416,667/mo FCF + 1.5 DSCR floors: $20MM
# asking, $900k/mo net flat month-over-month.
BIG_ASKING = 20_000_000
BIG_NET = 900_000


# ---------------------------------------------------------------------------
# Box config + evaluator wiring
# ---------------------------------------------------------------------------

def test_chad_box_config_loads():
    box = load_box("chad_5mm")
    assert box["label"] == "Chad 5MM+ EBITDA Box"
    assert box["owner_email"] == "Chad.Gardiner@griffinfingroup.com"
    assert box["min_free_cash_flow_mo"] == 416667
    assert box["min_dscr"] == 1.5
    assert box["trend_decline_tolerance"] == 0.05
    fin = box["financing"]
    assert fin["down_pct"] == 0.20
    assert fin["seller_note_rate"] == 0.07
    assert fin["seller_note_months"] == 60
    assert fin["heloc_rate"] == 0.085
    assert fin["heloc_interest_only"] is True


def test_load_box_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_box("does_not_exist")


def test_chad_box_verdicts():
    # A $600k deal cannot possibly clear a $416,667/mo FCF floor → out-of-box.
    small = evaluate_box(asking=600_000, ttm_avg_net=22_000, last_month_net=22_000,
                         config=load_box("chad_5mm"))
    assert small["box_pass"] is False
    assert small["fcf_pass"] is False

    # A large, flat deal clears every floor → in-box.
    big = evaluate_box(asking=BIG_ASKING, ttm_avg_net=BIG_NET, last_month_net=BIG_NET,
                       config=load_box("chad_5mm"))
    assert big["fcf_pass"] and big["dscr_pass"] and big["trend_pass"]
    assert big["box_pass"] is True
    # config_snapshot carries the box identity through for auditability.
    assert big["config_snapshot"]["label"] == "Chad 5MM+ EBITDA Box"


# ---------------------------------------------------------------------------
# Store: standalone intake scoring + persistence
# ---------------------------------------------------------------------------

def test_migration_14_creates_box_intake_results(store):
    assert store.migrate() == []  # already migrated by the fixture
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "box_intake_results" in tables


def test_score_box_intake_pass_and_roundtrip(store):
    intake = store.score_box_intake(
        box_id="chad_5mm", deal_name="MegaCorp", asking=BIG_ASKING,
        ttm_avg_net=BIG_NET, last_month_net=BIG_NET,
        submitter_name="Chad", submitter_email="chad@example.com",
        submitter_phone="+1-555-0100", notes="inbound")
    assert isinstance(intake, BoxIntakeResult)
    assert intake.id
    assert intake.box_pass is True
    assert intake.box_label == "Chad 5MM+ EBITDA Box"
    assert intake.owner_email == "Chad.Gardiner@griffinfingroup.com"

    fetched = store.get_box_intake_result(intake.id)
    assert fetched is not None
    assert fetched.box_pass is True
    assert fetched.deal_name == "MegaCorp"
    assert fetched.submitter_email == "chad@example.com"
    assert isinstance(fetched.box_reason, list) and fetched.box_reason
    assert isinstance(fetched.config_snapshot, dict)

    listed = store.list_box_intake_results(box_id="chad_5mm")
    assert [r.id for r in listed] == [intake.id]
    assert store.list_box_intake_results(box_id="other") == []


def test_score_box_intake_out_of_box(store):
    intake = store.score_box_intake(
        box_id="chad_5mm", deal_name="Tiny", asking=600_000,
        ttm_avg_net=22_000, last_month_net=22_000)
    assert intake.box_pass is False
    assert intake.fcf_pass is False


def test_email_status_update(store):
    intake = store.score_box_intake(
        box_id="chad_5mm", deal_name="MegaCorp", asking=BIG_ASKING,
        ttm_avg_net=BIG_NET, last_month_net=BIG_NET,
        submitter_email="chad@example.com")
    store.set_box_intake_email_status(intake.id, "sent")
    assert store.get_box_intake_result(intake.id).email_status == "sent"


# ---------------------------------------------------------------------------
# GmailSender contract (no credentials in the test env → graceful failure)
# ---------------------------------------------------------------------------

def _load_sender_module():
    path = os.path.join(REPO_MODULES, "outreach", "sender.py")
    spec = importlib.util.spec_from_file_location("eva_outreach_sender_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gmail_sender_without_credentials_does_not_raise(monkeypatch):
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    mod = _load_sender_module()
    sender = mod.GmailSender()
    msg = mod.OutboundMessage(
        to_email="x@example.com", to_name="X", subject="hi", body="b",
        disclosures_text="", sender_name="Vineet Ravi",
        sender_email="info@mangotecusa.com", sender_address="",
        campaign_id="c", recipient_id="r")
    result = sender.send(msg)
    assert result.ok is False
    assert result.provider == "gmail"
    assert "GMAIL_APP_PASSWORD" in result.error


def test_stub_sender_records_and_succeeds():
    mod = _load_sender_module()
    stub = mod.StubSender()
    msg = mod.OutboundMessage(
        to_email="x@example.com", to_name="X", subject="hi", body="b",
        disclosures_text="", sender_name="Vineet Ravi",
        sender_email="info@mangotecusa.com", sender_address="",
        campaign_id="c", recipient_id="r")
    result = stub.send(msg)
    assert result.ok is True
    assert stub.sent and stub.sent[0].to_email == "x@example.com"


def test_gmail_sender_unreachable_smtp_returns_error_not_raise(monkeypatch):
    # Credentials present, but the SMTP connection fails. The sender must
    # capture the error and return ok=False rather than raising. SMTP is MOCKED
    # to raise — no live network is touched.
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-xyz")
    mod = _load_sender_module()

    def _boom(*args, **kwargs):
        raise OSError("Name or service not known")

    monkeypatch.setattr(mod.smtplib, "SMTP", _boom)
    sender = mod.GmailSender()
    msg = mod.OutboundMessage(
        to_email="x@example.com", to_name="X", subject="hi", body="b",
        disclosures_text="", sender_name="Vineet Ravi",
        sender_email="info@mangotecusa.com", sender_address="",
        campaign_id="c", recipient_id="r")
    result = sender.send(msg)
    assert result.ok is False
    assert result.provider == "gmail"
    assert "Name or service not known" in result.error


# ---------------------------------------------------------------------------
# FastAPI endpoints (intake, results JSON + HTML, GHL webhook)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Legacy async layer is imported at main-module load but unused here.
    sys.modules.setdefault("aiosqlite", types.ModuleType("aiosqlite"))
    monkeypatch.setenv("EVA_OUTREACH_SENDER", "stub")
    try:
        from fastapi.testclient import TestClient
    except Exception:  # pragma: no cover - only if fastapi missing
        pytest.skip("fastapi TestClient unavailable")
    import main
    monkeypatch.setattr(main, "PIPELINE_DB_PATH", str(tmp_path / "endpoint.db"))
    # Instantiate without the `with` context so app lifespan (init_db) is not run.
    return TestClient(main.app)


def test_intake_endpoint_pass(client):
    r = client.post("/box/intake", json={
        "deal_name": "MegaCorp", "asking": BIG_ASKING,
        "ttm_avg_net": BIG_NET, "last_month_net": BIG_NET,
        "submitter_name": "Chad", "submitter_email": "chad@example.com"})
    assert r.status_code == 201
    body = r.json()
    assert body["box_pass"] is True
    assert body["email_status"] == "sent"          # stub sender always succeeds
    assert body["results_url"].endswith(f"/box/results/{body['id']}/page")

    got = client.get(f"/box/results/{body['id']}")
    assert got.status_code == 200 and got.json()["box_pass"] is True

    page = client.get(f"/box/results/{body['id']}/page")
    assert page.status_code == 200
    assert "IN BOX" in page.text and "<html" in page.text.lower()


def test_results_page_404(client):
    assert client.get("/box/results/nope").status_code == 404
    assert client.get("/box/results/nope/page").status_code == 404


def test_ghl_webhook_maps_fields_and_flags_placeholder(client):
    r = client.post("/box/ghl/intake", json={
        "business_name": "GHL Co", "asking_price": "25,000,000",
        "monthly_net": "1000000", "last_month": "1000000",
        "full_name": "Lead", "email": "lead@example.com"})
    assert r.status_code == 201
    body = r.json()
    assert body["deal_name"] == "GHL Co"
    assert body["asking"] == 25_000_000
    assert body["box_pass"] is True
    # Pipeline is still a placeholder → routing must be flagged not-ready and
    # must never be the protected Eva Acquisition pipeline id. The location now
    # defaults to the (safe) Mangotec location id.
    assert body["ghl"]["pipeline_id"] == "TODO_REPLACE_WITH_REAL_PIPELINE_ID"
    assert body["ghl"]["routing_ready"] is False
    assert body["ghl"]["routed"] is False
    assert body["ghl"]["pipeline_id"] != "hODxp7jDIraP6FaNZqNU"
    assert body["ghl"]["location_id"] == "kyK4yAY6Hur3F4deCx2n"


def test_intake_unknown_box_404(client):
    r = client.post("/box/intake", json={
        "deal_name": "X", "asking": 1_000_000, "ttm_avg_net": 50_000,
        "box_id": "no_such_box"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GHL webhook shared-secret enforcement
# ---------------------------------------------------------------------------

_GHL_PAYLOAD = {
    "business_name": "GHL Co", "asking_price": "25,000,000",
    "monthly_net": "1000000", "last_month": "1000000",
    "full_name": "Lead", "email": "lead@example.com",
}


def test_ghl_webhook_unconfigured_passes_through(client):
    import main
    # Secret unset (default) → route open, warns, accepts.
    assert main.GHL_WEBHOOK_SECRET == ""
    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD)
    assert r.status_code == 201


def test_ghl_webhook_valid_secret_passes(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "GHL_WEBHOOK_SECRET", "s3cr3t")
    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD,
                    headers={"X-Webhook-Secret": "s3cr3t"})
    assert r.status_code == 201


def test_ghl_webhook_wrong_secret_rejected(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "GHL_WEBHOOK_SECRET", "s3cr3t")
    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD,
                    headers={"X-Webhook-Secret": "nope"})
    assert r.status_code == 401


def test_ghl_webhook_missing_secret_rejected_when_configured(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "GHL_WEBHOOK_SECRET", "s3cr3t")
    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GHL contact routing (mocked highlevel client — no network)
# ---------------------------------------------------------------------------

class _FakeGHLClient:
    def __init__(self):
        self.contacts = []
        self.opportunities = []

    def upsert_contact(self, *, email="", name="", phone="", tags=None, source=""):
        cid = f"contact_{len(self.contacts) + 1}"
        self.contacts.append(
            {"id": cid, "email": email, "name": name, "tags": tags or []})
        return {"id": cid, "action": "created"}

    def add_contact_to_pipeline(self, contact_id, pipeline_id, stage_id):
        self.opportunities.append(
            {"contact_id": contact_id, "pipeline_id": pipeline_id,
             "stage_id": stage_id})
        return {"id": "opp_1"}


def test_ghl_webhook_routes_contact_when_configured(client, monkeypatch):
    import main
    fake = _FakeGHLClient()
    fake_mod = types.SimpleNamespace(build_client=lambda *a, **k: fake)
    monkeypatch.setattr(main, "GHL_CHAD_PIPELINE_ID", "real_pipe_123")
    monkeypatch.setattr(main, "GHL_CHAD_STAGE_ID", "stage_abc")
    monkeypatch.setattr(main, "_load_ghl_client", lambda: fake_mod)

    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD)
    assert r.status_code == 201
    ghl = r.json()["ghl"]
    assert ghl["routing_ready"] is True
    assert ghl["routed"] is True
    assert ghl["contact_id"] == "contact_1"
    assert ghl["pipeline_id"] == "real_pipe_123"
    # The upsert + opportunity-create path was exercised on the mock client.
    assert fake.contacts and fake.contacts[0]["email"] == "lead@example.com"
    assert fake.opportunities and fake.opportunities[0]["pipeline_id"] == "real_pipe_123"


def test_ghl_webhook_refuses_protected_pipeline(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "GHL_CHAD_PIPELINE_ID", "hODxp7jDIraP6FaNZqNU")
    r = client.post("/box/ghl/intake", json=_GHL_PAYLOAD)
    assert r.status_code == 201
    ghl = r.json()["ghl"]
    assert ghl["routing_ready"] is False
    assert ghl["routed"] is False
    assert "refused" in ghl.get("error", "")
