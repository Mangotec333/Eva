"""Tests for the post-scoring "deal box" hard-criteria evaluator (network-free).

Covers the financing math on a sample deal, in-box / out-of-box verdicts, a
declining deal (#95198-style: last month 29% below the TTM average) failing the
trend gate, config loading/override, and migration idempotency + the
store.evaluate_box wiring on a scored deal.
"""

from __future__ import annotations

import json

import pytest

from box_evaluator import DEFAULT_CONFIG, amortized_payment, evaluate_box, load_config
from pipeline_models import RawDeal, ScoredDeal

# A $600k asking deal financed 20% down: seller note on 80% amortized over 60mo
# at 7%, interest-only HELOC on the 20% down at 8.5%.
ASKING = 600_000


def test_box_math_sample_deal():
    result = evaluate_box(asking=ASKING, ttm_avg_net=22_000, last_month_net=22_000)

    # amort(480k, 7%, 60) ≈ 9504.58 ; heloc = 120k*8.5%/12 = 850
    assert result["seller_note_pmt"] == pytest.approx(
        amortized_payment(0.8 * ASKING, 0.07, 60), abs=0.01)
    assert result["seller_note_pmt"] == pytest.approx(9504.58, abs=0.01)
    assert result["heloc_pmt"] == pytest.approx(850.0, abs=0.01)
    assert result["total_debt"] == pytest.approx(
        result["seller_note_pmt"] + result["heloc_pmt"], rel=1e-9)
    assert result["free_cash_flow"] == pytest.approx(
        22_000 - result["total_debt"], rel=1e-9)
    assert result["dscr"] == pytest.approx(22_000 / result["total_debt"], abs=1e-3)
    assert result["monthly_net_used"] == 22_000  # current run-rate = last month


def test_in_box_and_out_of_box_verdicts():
    # Strong, flat cash flow clears every floor → in-box.
    good = evaluate_box(asking=ASKING, ttm_avg_net=22_000, last_month_net=22_000)
    assert good["fcf_pass"] and good["dscr_pass"] and good["trend_pass"]
    assert good["box_pass"] is True

    # Thin cash flow: FCF below the $10k floor and DSCR below 1.5 → out-of-box.
    weak = evaluate_box(asking=ASKING, ttm_avg_net=15_000, last_month_net=15_000)
    assert weak["fcf_pass"] is False
    assert weak["dscr_pass"] is False
    assert weak["box_pass"] is False


def test_declining_deal_fails_trend():
    # #95198-style: last month is 29% below the trailing-twelve-month average,
    # well beyond the 5% decline tolerance → trend fails → out-of-box, even
    # though the TTM average alone would clear the cash-flow floors.
    ttm_avg = 22_000
    last_month = round(ttm_avg * 0.71)  # 29% decline
    result = evaluate_box(asking=ASKING, ttm_avg_net=ttm_avg, last_month_net=last_month)

    assert result["trend_pass"] is False
    assert result["box_pass"] is False
    assert any("declining" in r.lower() for r in result["box_reason"])

    # With no last-month figure the trend gate cannot pass (conservative default).
    no_lm = evaluate_box(asking=ASKING, ttm_avg_net=ttm_avg, last_month_net=None)
    assert no_lm["trend_pass"] is False
    assert no_lm["monthly_net_used"] == ttm_avg  # falls back to the TTM average


def test_config_loading(tmp_path):
    # Defaults load when no file override is given.
    base = load_config(path=str(tmp_path / "missing.json"))
    assert base["min_free_cash_flow_mo"] == DEFAULT_CONFIG["min_free_cash_flow_mo"]
    assert base["financing"]["seller_note_months"] == 60

    # A partial override file is merged over the defaults (incl. nested financing).
    cfg_path = tmp_path / "deal_box_config.json"
    cfg_path.write_text(json.dumps({
        "min_free_cash_flow_mo": 5_000,
        "financing": {"down_pct": 0.10},
    }))
    cfg = load_config(path=str(cfg_path))
    assert cfg["min_free_cash_flow_mo"] == 5_000
    assert cfg["financing"]["down_pct"] == 0.10          # overridden
    assert cfg["financing"]["seller_note_rate"] == 0.07  # default preserved

    # The override actually changes the verdict: a deal that fails at the $10k
    # floor passes at the relaxed $5k floor.
    relaxed = evaluate_box(asking=ASKING, ttm_avg_net=16_000, last_month_net=16_000,
                           config=cfg)
    assert relaxed["config_snapshot"]["min_free_cash_flow_mo"] == 5_000


def test_box_migration_idempotent_and_store_eval(store):
    # store fixture already migrated; re-running applies nothing new.
    assert store.migrate() == []
    tables = {r[0] for r in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "deal_box_evaluations" in tables

    # Evaluating an unscored deal is refused — the box is a post-scoring layer.
    raw, _ = store.upsert_raw_deal(RawDeal(
        id="", source="empire_flippers", listing_id="600k",
        name="Box Candidate", asking_price=ASKING, monthly_net=22_000,
        raw_json=json.dumps({"last_month_net": 22_000, "ttm_avg_net": 22_000})))
    with pytest.raises(ValueError):
        store.evaluate_box(raw.id)

    # Mark it scored, then the box evaluates + persists an in-box verdict.
    store.save_scored_deal(ScoredDeal(id="", raw_deal_id=raw.id, overall_score=8.0))
    ev = store.evaluate_box(raw.id)
    assert ev.box_pass is True
    assert ev.deal_id == raw.id

    fetched = store.get_box_eval(raw.id)
    assert fetched is not None and fetched.box_pass is True
    assert fetched.box_reason and isinstance(fetched.box_reason, list)

    box_deals = store.list_box_deals()
    assert [b.deal_id for b in box_deals] == [raw.id]

    # Re-evaluating upserts (no duplicate row).
    store.evaluate_box(raw.id)
    assert len(store.list_box_deals()) == 1
