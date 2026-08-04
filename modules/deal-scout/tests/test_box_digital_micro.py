"""Tests for the ``digital_micro`` box profile (network-free).

Covers the cash-funded criteria math (payback / margin / churn / price / trend),
the advisory flags, config loading for the second profile, box-type validation,
and the widened (deal_id, box_type) uniqueness that lets one deal hold a verdict
under both profiles.
"""

from __future__ import annotations

import json

import pytest

from box_evaluator import (
    BOX_TYPE_DIGITAL_MICRO,
    DIGITAL_MICRO_DEFAULT_CONFIG,
    evaluate_box,
    load_config,
    normalize_box_type,
)
from pipeline_models import RawDeal, ScoredDeal

# $60k asking, $5k/mo net on $10k/mo revenue: 12-month payback at a 50% margin.
IN_BOX = dict(
    asking=60_000, ttm_avg_net=5_000, last_month_net=5_000,
    last_month_revenue=10_000, monthly_churn=0.03, age_months=24,
    box_type=BOX_TYPE_DIGITAL_MICRO,
)


def test_digital_micro_in_box_math():
    result = evaluate_box(**IN_BOX)

    assert result["box_type"] == BOX_TYPE_DIGITAL_MICRO
    assert result["payback_months"] == pytest.approx(12.0)
    assert result["net_margin"] == pytest.approx(0.5)
    assert result["monthly_churn"] == pytest.approx(0.03)
    assert result["price_pass"] and result["payback_pass"]
    assert result["margin_pass"] and result["churn_pass"] and result["trend_pass"]
    assert result["box_pass"] is True
    assert result["flags"] == []

    # A cash-funded acquisition models no debt at all.
    assert result["seller_note_pmt"] == 0.0
    assert result["heloc_pmt"] == 0.0
    assert result["total_debt"] == 0.0
    assert result["dscr"] == 0.0
    assert result["free_cash_flow"] == pytest.approx(5_000)


def test_payback_none_without_positive_last_month_net():
    for lm in (0, -250):
        result = evaluate_box(**{**IN_BOX, "last_month_net": lm})
        assert result["payback_months"] is None
        assert result["payback_pass"] is False
        assert result["box_pass"] is False
        assert any("no positive last-month net" in r for r in result["box_reason"])

    # No last-month figure at all: payback and trend both fail, and the TTM
    # average is used as the run-rate net.
    none_lm = evaluate_box(**{**IN_BOX, "last_month_net": None})
    assert none_lm["payback_months"] is None
    assert none_lm["trend_pass"] is False
    assert none_lm["monthly_net_used"] == pytest.approx(5_000)


def test_margin_falls_back_to_ttm_pair():
    # Without a last-month revenue figure the margin comes from the TTM pair.
    result = evaluate_box(**{**IN_BOX, "last_month_revenue": None,
                             "ttm_revenue": 120_000, "ttm_profit": 60_000})
    assert result["net_margin"] == pytest.approx(0.5)
    assert result["margin_pass"] is True

    # With neither pair available the margin gate cannot pass.
    blind = evaluate_box(**{**IN_BOX, "last_month_revenue": None})
    assert blind["net_margin"] is None
    assert blind["margin_pass"] is False
    assert blind["box_pass"] is False
    assert any("no revenue figure" in r for r in blind["box_reason"])


def test_margin_below_floor_fails():
    # $5k net on $20k revenue = 25% margin, below the 40% floor.
    result = evaluate_box(**{**IN_BOX, "last_month_revenue": 20_000})
    assert result["net_margin"] == pytest.approx(0.25)
    assert result["margin_pass"] is False
    assert result["box_pass"] is False


def test_churn_ceiling_warn_band_and_hard_fail():
    # At/below the 5% ceiling: clean pass, no flag.
    ok = evaluate_box(**{**IN_BOX, "monthly_churn": 0.05})
    assert ok["churn_pass"] is True and ok["flags"] == []

    # Between the ceiling and the 10% hard-fail line: fails the gate AND raises
    # the advisory warn flag.
    warn = evaluate_box(**{**IN_BOX, "monthly_churn": 0.075})
    assert warn["churn_pass"] is False
    assert warn["box_pass"] is False
    assert "high_churn_warn" in warn["flags"]

    # Above the hard-fail line: still fails, but it is past the warn band.
    hard = evaluate_box(**{**IN_BOX, "monthly_churn": 0.20})
    assert hard["churn_pass"] is False
    assert "high_churn_warn" not in hard["flags"]

    # Unreported churn is not held against the deal.
    unknown = evaluate_box(**{**IN_BOX, "monthly_churn": None})
    assert unknown["monthly_churn"] is None
    assert unknown["churn_pass"] is True
    assert unknown["box_pass"] is True
    assert any("not reported" in r for r in unknown["box_reason"])


def test_thin_track_record_flag_is_advisory():
    young = evaluate_box(**{**IN_BOX, "age_months": 6})
    assert "thin_track_record" in young["flags"]
    # The flag is advisory only — it does not by itself push the deal out of box.
    assert young["box_pass"] is True

    assert evaluate_box(**{**IN_BOX, "age_months": 12})["flags"] == []
    assert evaluate_box(**{**IN_BOX, "age_months": None})["flags"] == []


def test_price_cap_and_payback_ceiling():
    over_cap = evaluate_box(**{**IN_BOX, "asking": 200_000})
    assert over_cap["price_pass"] is False
    assert over_cap["box_pass"] is False

    # $150k at $5k/mo = 30 months, past the 18-month payback ceiling (the price
    # cap itself still passes at exactly $150k).
    slow = evaluate_box(**{**IN_BOX, "asking": 150_000})
    assert slow["price_pass"] is True
    assert slow["payback_months"] == pytest.approx(30.0)
    assert slow["payback_pass"] is False
    assert slow["box_pass"] is False


def test_declining_deal_fails_trend():
    result = evaluate_box(**{**IN_BOX, "last_month_net": 3_000,
                             "last_month_revenue": 6_000})
    assert result["trend_pass"] is False
    assert result["box_pass"] is False
    assert any("declining" in r.lower() for r in result["box_reason"])

    # Within the 5% decline tolerance the trend still passes.
    tolerated = evaluate_box(**{**IN_BOX, "last_month_net": 4_800,
                                "last_month_revenue": 9_600})
    assert tolerated["trend_pass"] is True


def test_digital_micro_config_loading(tmp_path):
    cfg = load_config(box_type=BOX_TYPE_DIGITAL_MICRO)
    assert cfg["max_payback_months"] == DIGITAL_MICRO_DEFAULT_CONFIG["max_payback_months"]
    assert cfg["churn_hard_fail"] == 0.10
    # The cash-funded profile carries no financing block.
    assert "financing" not in cfg
    # ...while the default profile is untouched by the new one.
    assert "financing" in load_config()

    override = tmp_path / "digital_micro.json"
    override.write_text(json.dumps({"max_payback_months": 36, "min_net_margin": 0.20}))
    relaxed = load_config(path=str(override), box_type=BOX_TYPE_DIGITAL_MICRO)
    assert relaxed["max_payback_months"] == 36
    assert relaxed["min_net_margin"] == 0.20
    assert relaxed["max_asking_price"] == 150_000  # default preserved

    # The override flips the verdict on a deal that fails at the shipped ceiling.
    slow = dict(IN_BOX, asking=150_000, last_month_revenue=20_000)
    assert evaluate_box(**slow)["box_pass"] is False
    assert evaluate_box(**slow, config=relaxed)["box_pass"] is True


def test_normalize_box_type():
    assert normalize_box_type(None) == "real_estate"
    assert normalize_box_type("") == "real_estate"
    assert normalize_box_type("  Digital_Micro ") == BOX_TYPE_DIGITAL_MICRO
    with pytest.raises(ValueError, match="unknown box_type"):
        normalize_box_type("crypto")
    with pytest.raises(ValueError):
        evaluate_box(asking=1, ttm_avg_net=1, box_type="crypto")


def test_both_profiles_coexist_on_one_deal(store):
    # The store fixture is already migrated; re-running applies nothing new.
    assert store.migrate() == []
    cols = {r[1] for r in store.conn.execute(
        "PRAGMA table_info(deal_box_evaluations)").fetchall()}
    assert {"box_type", "payback_months", "net_margin", "monthly_churn",
            "age_months", "flags"} <= cols

    raw, _ = store.upsert_raw_deal(RawDeal(
        id="", source="acquire_com", listing_id="micro-1", name="Micro SaaS",
        asking_price=60_000, monthly_net=5_000, age_years=2.0,
        raw_json=json.dumps({
            "ttm_avg_net": 5_000, "last_month_net": 5_000,
            "last_month_revenue": 10_000, "ttm_revenue": 120_000,
            "ttm_profit": 60_000, "monthly_churn": 0.03, "age_months": 24,
        })))
    store.save_scored_deal(ScoredDeal(id="", raw_deal_id=raw.id, overall_score=7.0))

    micro = store.evaluate_box(raw.id, box_type=BOX_TYPE_DIGITAL_MICRO)
    assert micro.box_type == BOX_TYPE_DIGITAL_MICRO
    assert micro.box_pass is True
    assert micro.payback_months == pytest.approx(12.0)
    assert micro.net_margin == pytest.approx(0.5)

    # The same deal under the debt-financed profile is far out of box.
    re_ev = store.evaluate_box(raw.id, box_type="real_estate")
    assert re_ev.box_type == "real_estate"
    assert re_ev.box_pass is False
    assert re_ev.id != micro.id

    assert store.get_box_eval(raw.id, box_type=BOX_TYPE_DIGITAL_MICRO).id == micro.id
    assert store.get_box_eval(raw.id).id == re_ev.id

    # Re-evaluating upserts per (deal_id, box_type) rather than duplicating.
    store.evaluate_box(raw.id, box_type=BOX_TYPE_DIGITAL_MICRO)
    rows = store.conn.execute(
        "SELECT box_type FROM deal_box_evaluations WHERE deal_id=?", (raw.id,)).fetchall()
    assert sorted(r[0] for r in rows) == ["digital_micro", "real_estate"]

    assert [b.deal_id for b in store.list_box_deals(box_type=BOX_TYPE_DIGITAL_MICRO)] == [raw.id]
    assert store.list_box_deals(box_type="real_estate") == []
    assert [b.box_type for b in store.list_box_deals()] == [BOX_TYPE_DIGITAL_MICRO]
