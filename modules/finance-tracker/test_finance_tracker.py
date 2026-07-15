"""
EVA Treasurer — offline test suite (stub ledger, zero network). Nothing real
(Slack / eva-state) is ever fired: SLACK_BOT_TOKEN is cleared and the state
client is a stub.

Stdlib-only runner (no pytest dependency), so it runs anywhere the module runs:

  python modules/finance-tracker/test_finance_tracker.py
  (or)  cd modules/finance-tracker && python test_finance_tracker.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EVA_TREASURER_OFFLINE"] = "1"
os.environ.pop("SLACK_BOT_TOKEN", None)  # ensure Slack never fires

import finance_tracker as core
import store
from service import TreasurerService
from state_client import StubStateLedgerClient


# ---------------------------------------------------------------------------
# Helpers (framework-free)
# ---------------------------------------------------------------------------

def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="treasurer_test_", suffix=".db")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    store.init_db(path)
    return path


def _svc(db, state=None):
    return TreasurerService(db_path=db,
                            state=state or StubStateLedgerClient(),
                            offline=True)


# ---------------------------------------------------------------------------
# Category normalisation
# ---------------------------------------------------------------------------

def test_normalise_known_and_alias():
    assert core.normalise_category("llm_api") == core.CAT_LLM_API
    assert core.normalise_category("Anthropic") == core.CAT_LLM_API
    assert core.normalise_category("GHL") == core.CAT_SUBSCRIPTIONS
    assert core.normalise_category("Empire Flippers") == core.CAT_MARKETPLACE_FEES
    assert core.normalise_category("ads") == core.CAT_AD_SPEND


def test_normalise_unknown_is_other():
    assert core.normalise_category("wibble") == core.CAT_OTHER
    assert core.normalise_category("") == core.CAT_OTHER
    assert core.normalise_category(None) == core.CAT_OTHER


# ---------------------------------------------------------------------------
# Period windows
# ---------------------------------------------------------------------------

def test_period_start_month_is_first():
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    assert core.period_start("month", now).day == 1


def test_period_start_week_is_monday():
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)  # a Wednesday
    assert core.period_start("week", now).weekday() == 0


# ---------------------------------------------------------------------------
# Budget usage classification
# ---------------------------------------------------------------------------

def test_usage_status_bands():
    assert core.usage_status(50, 100)["status"] == "ok"
    assert core.usage_status(80, 100)["status"] == "warn"
    assert core.usage_status(100, 100)["status"] == "over"
    assert core.usage_status(120, 100)["over_cents"] == 20
    assert core.usage_status(10, 0)["status"] == "uncapped"


def test_crossed_threshold_only_on_crossing():
    assert core.crossed_threshold(0, 80, 100) == "warn"
    assert core.crossed_threshold(80, 90, 100) is None       # already warned
    assert core.crossed_threshold(90, 100, 100) == "over"
    assert core.crossed_threshold(100, 110, 100) is None      # already over
    assert core.crossed_threshold(0, 50, 0) is None           # uncapped


# ---------------------------------------------------------------------------
# Burn projection
# ---------------------------------------------------------------------------

def test_project_month_runrate():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)  # day 10 of a 31-day month
    proj = core.project_month(1000, now=now)
    assert proj["daily_rate_cents"] == 100
    assert proj["projected_month_cents"] == 3100


# ---------------------------------------------------------------------------
# store idempotency
# ---------------------------------------------------------------------------

def test_store_idempotent_event_key():
    db = _new_db()
    a = store.add_event(category="llm_api", amount_cents=500, event_key="k1", path=db)
    b = store.add_event(category="llm_api", amount_cents=500, event_key="k1", path=db)
    assert a["duplicate"] is False
    assert b["duplicate"] is True
    assert store.category_total("llm_api", path=db) == 500


def test_store_content_signature_dedup():
    db = _new_db()
    ts = "2026-07-15T00:00:00+00:00"
    store.add_event(category="ad_spend", amount_cents=200, vendor="meta",
                    timestamp=ts, path=db)
    dup = store.add_event(category="ad_spend", amount_cents=200, vendor="meta",
                          timestamp=ts, path=db)
    assert dup["duplicate"] is True
    assert store.category_total("ad_spend", path=db) == 200


# ---------------------------------------------------------------------------
# service.track — log, aggregate, alert, learn
# ---------------------------------------------------------------------------

def test_track_logs_and_emits():
    db = _new_db()
    state = StubStateLedgerClient()
    res = _svc(db, state=state).track(category="anthropic", amount_cents=1299,
                                      vendor="Anthropic", source_agent="diracatron")
    assert res["ok"] is True
    assert res["category"] == core.CAT_LLM_API
    assert any(e["event_type"] == "spend_logged" for e in state.events)


def test_track_duplicate_does_not_double_count():
    db = _new_db()
    svc = _svc(db)
    svc.track(category="llm_api", amount_cents=1000, event_key="dup")
    again = svc.track(category="llm_api", amount_cents=1000, event_key="dup")
    assert again["duplicate"] is True
    assert svc.summary("month")["by_category"]["llm_api"] == 1000


def test_track_rejects_bad_amount():
    db = _new_db()
    res = _svc(db).track(category="other", amount_cents=-5)
    assert res["ok"] is False


def test_track_fires_alert_on_breach():
    db = _new_db()
    state = StubStateLedgerClient()
    svc = _svc(db, state=state)
    svc.set_budget(category="ad_spend", cap_cents=1000, period="month")
    # first spend stays under 80%
    r1 = svc.track(category="ad_spend", amount_cents=700)
    assert r1["alert"] is None
    # crosses 80% -> warn alert (Slack unconfigured => honest ok=False, no network)
    r2 = svc.track(category="ad_spend", amount_cents=200)
    assert r2["alert"] is not None
    assert r2["alert"]["threshold"] == "warn"
    assert r2["alert"]["slack"]["ok"] is False
    assert any(e["event_type"] == "budget_breach" for e in state.events)
    # crosses 100% -> over alert
    r3 = svc.track(category="ad_spend", amount_cents=200)
    assert r3["alert"]["threshold"] == "over"


def test_summary_by_category():
    db = _new_db()
    svc = _svc(db)
    svc.track(category="llm_api", amount_cents=300)
    svc.track(category="subscriptions", amount_cents=1200)
    s = svc.summary("month")
    assert s["by_category"]["llm_api"] == 300
    assert s["by_category"]["subscriptions"] == 1200
    assert s["total_cents"] == 1500


def test_budget_caps_vs_actual():
    db = _new_db()
    svc = _svc(db)
    svc.set_budget(category="hosting_domains", cap_cents=5000)
    svc.track(category="hosting_domains", amount_cents=4000)
    b = svc.budget()
    row = next(r for r in b["categories"] if r["category"] == "hosting_domains")
    assert row["cap_cents"] == 5000
    assert row["actual_cents"] == 4000
    assert row["status"] == "warn"  # 80%
    assert b["total_cap_cents"] == 5000


def test_set_budget_normalises_category():
    db = _new_db()
    res = _svc(db).set_budget(category="Anthropic", cap_cents=10000)
    assert res["ok"] is True
    assert res["budget"]["category"] == core.CAT_LLM_API


def test_export_csv_has_header_and_rows():
    db = _new_db()
    svc = _svc(db)
    svc.track(category="deal_costs", amount_cents=25000, vendor="lawyer")
    csv_txt = svc.export_csv()
    lines = [l for l in csv_txt.splitlines() if l.strip()]
    assert lines[0].startswith("timestamp,category,amount_cents")
    assert any("deal_costs" in l for l in lines[1:])


def test_burn_projection_and_cap():
    db = _new_db()
    svc = _svc(db)
    svc.set_budget(category="llm_api", cap_cents=100000)
    svc.track(category="llm_api", amount_cents=5000)
    burn = svc.burn()
    assert burn["month_to_date_cents"] == 5000
    assert burn["projected_month_cents"] >= 5000
    assert "projected_vs_cap" in burn
    assert burn["total_monthly_cap_cents"] == 100000


def test_daily_summary_emits():
    db = _new_db()
    state = StubStateLedgerClient()
    svc = _svc(db, state=state)
    svc.track(category="other", amount_cents=100)
    res = svc.daily_summary()
    assert res["ok"] is True
    assert any(e["event_type"] == "spend_daily_summary" for e in state.events)


def test_slack_alert_no_token():
    os.environ.pop("SLACK_BOT_TOKEN", None)
    res = core.slack_alert("hello")
    assert res["ok"] is False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {t.__name__}")
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
