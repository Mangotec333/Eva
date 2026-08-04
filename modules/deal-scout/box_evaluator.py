"""
EVA Deal Scout — "deal box" hard-criteria evaluator.

This is a POST-SCORING layer.  Scoring still runs on every US-eligible deal
(the score gate is untouched); the box then tags an already-scored deal as
``in-box`` (a stable-base acquisition candidate) or ``out-of-box`` by testing it
against hard financeability criteria at the CURRENT run-rate.

The evaluation models the intended financing structure:

    down payment      = down_pct * asking                      (funded by a HELOC)
    seller note       = (1 - down_pct) * asking                (amortized)
    seller_note_pmt   = amort(seller_note, seller_note_rate, seller_note_months)
    heloc_pmt         = down_pct * asking * heloc_rate / 12     (interest-only)
    total_debt        = seller_note_pmt + heloc_pmt
    free_cash_flow    = monthly_net - total_debt
    dscr              = monthly_net / total_debt

A deal is in-box iff free cash flow clears the floor, DSCR clears the floor, AND
the recent trend is flat-or-growing (last month within tolerance of the TTM
average).  ``run_rate="current"`` uses ``last_month_net`` as the monthly net,
falling back to the TTM average when a last-month figure is not available.

The criteria live in ``deal_box_config.json`` and can be adjusted without code
changes; ``load_config`` merges an on-disk file over the built-in defaults.

A second box profile, ``digital_micro``, evaluates cash-funded micro-SaaS /
digital acquisitions (Acquire.com / Flippa / Empire Flippers style listings).
It runs no financing math at all — the criteria are payback period, net margin,
monthly churn and the same flat-or-growing trend gate.  Its criteria live in
``deal_box_config_digital_micro.json``.  Select a profile with the ``box_type``
argument; ``real_estate`` remains the default and is unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

CONFIG_FILENAME = "deal_box_config.json"
DIGITAL_MICRO_CONFIG_FILENAME = "deal_box_config_digital_micro.json"

BOX_TYPE_REAL_ESTATE = "real_estate"
BOX_TYPE_DIGITAL_MICRO = "digital_micro"
BOX_TYPES: tuple[str, ...] = (BOX_TYPE_REAL_ESTATE, BOX_TYPE_DIGITAL_MICRO)

DEFAULT_CONFIG: dict[str, Any] = {
    "min_free_cash_flow_mo": 10000,
    "min_dscr": 1.5,
    "trend_decline_tolerance": 0.05,
    "financing": {
        "down_pct": 0.20,
        "seller_note_rate": 0.07,
        "seller_note_months": 60,
        "heloc_rate": 0.085,
        "heloc_interest_only": True,
        "run_rate": "current",
    },
}

# Cash-funded micro-acquisition profile.  ``max_monthly_churn`` is the pass
# ceiling; churn between it and ``churn_hard_fail`` additionally raises a
# ``high_churn_warn`` flag.
DIGITAL_MICRO_DEFAULT_CONFIG: dict[str, Any] = {
    "max_asking_price": 150000,
    "max_payback_months": 18,
    "min_net_margin": 0.40,
    "max_monthly_churn": 0.05,
    "churn_hard_fail": 0.10,
    "min_age_months": 12,
    "trend_decline_tolerance": 0.05,
}

_PROFILES: dict[str, tuple[str, dict[str, Any]]] = {
    BOX_TYPE_REAL_ESTATE: (CONFIG_FILENAME, DEFAULT_CONFIG),
    BOX_TYPE_DIGITAL_MICRO: (DIGITAL_MICRO_CONFIG_FILENAME, DIGITAL_MICRO_DEFAULT_CONFIG),
}


def normalize_box_type(box_type: Optional[str]) -> str:
    """Validate/normalize a box profile name, defaulting to ``real_estate``."""
    key = (box_type or BOX_TYPE_REAL_ESTATE).strip().lower()
    if key not in _PROFILES:
        raise ValueError(
            f"unknown box_type {box_type!r} (expected one of {', '.join(BOX_TYPES)})")
    return key


def _default_config_path(box_type: str = BOX_TYPE_REAL_ESTATE) -> str:
    filename = _PROFILES[normalize_box_type(box_type)][0]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def load_config(path: Optional[str] = None,
                box_type: str = BOX_TYPE_REAL_ESTATE) -> dict[str, Any]:
    """Return the box config: on-disk file (if present) merged over defaults.

    Nested ``financing`` keys are merged individually so a partial config file
    only needs to override the keys it wants to change.
    """
    box_type = normalize_box_type(box_type)
    defaults = _PROFILES[box_type][1]
    cfg: dict[str, Any] = dict(defaults)
    if "financing" in defaults:
        cfg["financing"] = dict(defaults["financing"])
    path = path or _default_config_path(box_type)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        cfg.update({k: v for k, v in loaded.items() if k != "financing"})
        if "financing" in defaults:
            cfg["financing"] = {**defaults["financing"], **(loaded.get("financing") or {})}
    return cfg


def amortized_payment(principal: float, annual_rate: float, months: int) -> float:
    """Fixed monthly payment that fully amortizes ``principal`` over ``months``.

    Falls back to straight-line (principal / months) when the rate is zero.
    """
    if months <= 0 or principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / months
    factor = (1 + r) ** months
    return principal * r * factor / (factor - 1)


def evaluate_box(
    *,
    asking: float,
    ttm_avg_net: float,
    last_month_net: Optional[float] = None,
    config: Optional[dict[str, Any]] = None,
    box_type: str = BOX_TYPE_REAL_ESTATE,
    last_month_revenue: Optional[float] = None,
    ttm_revenue: Optional[float] = None,
    ttm_profit: Optional[float] = None,
    monthly_churn: Optional[float] = None,
    age_months: Optional[float] = None,
) -> dict[str, Any]:
    """Evaluate a deal against the criteria of the selected box profile.

    ``box_type="real_estate"`` (the default) runs the debt-financed evaluation
    described in the module docstring.  ``box_type="digital_micro"`` runs the
    cash-funded micro-acquisition evaluation and ignores the financing keys.
    """
    if normalize_box_type(box_type) == BOX_TYPE_DIGITAL_MICRO:
        return _evaluate_digital_micro(
            asking=asking,
            ttm_avg_net=ttm_avg_net,
            last_month_net=last_month_net,
            config=config,
            last_month_revenue=last_month_revenue,
            ttm_revenue=ttm_revenue,
            ttm_profit=ttm_profit,
            monthly_churn=monthly_churn,
            age_months=age_months,
        )
    cfg = config or load_config()
    fin = cfg["financing"]
    down_pct = float(fin["down_pct"])
    asking = float(asking or 0.0)

    seller_note_principal = (1 - down_pct) * asking
    seller_note_pmt = amortized_payment(
        seller_note_principal, float(fin["seller_note_rate"]), int(fin["seller_note_months"])
    )
    heloc_pmt = down_pct * asking * float(fin["heloc_rate"]) / 12.0
    total_debt = seller_note_pmt + heloc_pmt

    # Run-rate selection.  "current" prefers last month, falling back to the TTM
    # average; any other setting uses the TTM average.
    ttm_avg_net = float(ttm_avg_net or 0.0)
    has_last_month = last_month_net is not None
    lm = float(last_month_net) if has_last_month else None
    if fin.get("run_rate", "current") == "current" and lm is not None:
        monthly_net_used = lm
    else:
        monthly_net_used = ttm_avg_net

    free_cash_flow = monthly_net_used - total_debt
    dscr = (monthly_net_used / total_debt) if total_debt > 0 else 0.0

    tol = float(cfg["trend_decline_tolerance"])
    trend_pass = (lm >= ttm_avg_net * (1 - tol)) if (has_last_month and ttm_avg_net > 0) else False

    min_fcf = float(cfg["min_free_cash_flow_mo"])
    min_dscr = float(cfg["min_dscr"])
    fcf_pass = free_cash_flow >= min_fcf
    dscr_pass = dscr >= min_dscr
    box_pass = fcf_pass and dscr_pass and trend_pass

    box_reason = [
        f"free_cash_flow ${free_cash_flow:,.0f}/mo "
        f"{'>=' if fcf_pass else '<'} ${min_fcf:,.0f} floor: "
        f"{'PASS' if fcf_pass else 'FAIL'}",
        f"dscr {dscr:.2f} {'>=' if dscr_pass else '<'} {min_dscr:.2f} floor: "
        f"{'PASS' if dscr_pass else 'FAIL'}",
        _trend_reason(trend_pass, has_last_month, lm, ttm_avg_net, tol),
    ]

    return {
        "box_type": BOX_TYPE_REAL_ESTATE,
        "asking": round(asking, 2),
        "monthly_net_used": round(monthly_net_used, 2),
        "ttm_avg_net": round(ttm_avg_net, 2),
        "last_month_net": round(lm, 2) if lm is not None else None,
        "seller_note_pmt": round(seller_note_pmt, 2),
        "heloc_pmt": round(heloc_pmt, 2),
        "total_debt": round(total_debt, 2),
        "free_cash_flow": round(free_cash_flow, 2),
        "dscr": round(dscr, 4),
        "fcf_pass": fcf_pass,
        "dscr_pass": dscr_pass,
        "trend_pass": trend_pass,
        "box_pass": box_pass,
        "box_reason": box_reason,
        "flags": [],
        "config_snapshot": cfg,
    }


def _evaluate_digital_micro(
    *,
    asking: float,
    ttm_avg_net: float,
    last_month_net: Optional[float],
    config: Optional[dict[str, Any]],
    last_month_revenue: Optional[float],
    ttm_revenue: Optional[float],
    ttm_profit: Optional[float],
    monthly_churn: Optional[float],
    age_months: Optional[float],
) -> dict[str, Any]:
    """Cash-funded micro-acquisition box: payback, margin, churn, trend.

    No debt is modelled, so the financing fields of the shared result shape are
    zeroed and ``free_cash_flow`` is simply the monthly net used.
    """
    cfg = config or load_config(box_type=BOX_TYPE_DIGITAL_MICRO)
    asking = float(asking or 0.0)
    ttm_avg_net = float(ttm_avg_net or 0.0)
    lm = float(last_month_net) if last_month_net is not None else None
    monthly_net_used = lm if lm is not None else ttm_avg_net

    max_asking = float(cfg["max_asking_price"])
    max_payback = float(cfg["max_payback_months"])
    min_margin = float(cfg["min_net_margin"])
    max_churn = float(cfg["max_monthly_churn"])
    churn_hard_fail = float(cfg.get("churn_hard_fail", 0.10))
    min_age = float(cfg["min_age_months"])
    tol = float(cfg["trend_decline_tolerance"])

    payback_months = (asking / lm) if (lm is not None and lm > 0) else None

    # Margin prefers the last-month figures and falls back to the TTM pair.
    margin: Optional[float] = None
    if lm is not None and last_month_revenue:
        margin = lm / float(last_month_revenue)
    elif ttm_revenue and ttm_profit is not None:
        margin = float(ttm_profit) / float(ttm_revenue)

    churn = float(monthly_churn) if monthly_churn is not None else None

    price_pass = asking <= max_asking
    payback_pass = payback_months is not None and payback_months <= max_payback
    margin_pass = margin is not None and margin >= min_margin
    churn_pass = churn is None or churn <= max_churn
    trend_pass = (lm >= ttm_avg_net * (1 - tol)) if (lm is not None and ttm_avg_net > 0) else False

    box_pass = price_pass and payback_pass and margin_pass and churn_pass and trend_pass

    flags: list[str] = []
    if age_months is not None and float(age_months) < min_age:
        flags.append("thin_track_record")
    if churn is not None and max_churn < churn <= churn_hard_fail:
        flags.append("high_churn_warn")

    box_reason = [
        f"asking ${asking:,.0f} {'<=' if price_pass else '>'} ${max_asking:,.0f} cap: "
        f"{'PASS' if price_pass else 'FAIL'}",
        (f"payback {payback_months:.1f}mo {'<=' if payback_pass else '>'} "
         f"{max_payback:.0f}mo: {'PASS' if payback_pass else 'FAIL'}")
        if payback_months is not None else
        "payback: FAIL (no positive last-month net to amortize the price against)",
        (f"net_margin {margin:.1%} {'>=' if margin_pass else '<'} {min_margin:.0%} floor: "
         f"{'PASS' if margin_pass else 'FAIL'}")
        if margin is not None else "net_margin: FAIL (no revenue figure available)",
        (f"monthly_churn {churn:.1%} {'<=' if churn_pass else '>'} {max_churn:.0%} ceiling: "
         f"{'PASS' if churn_pass else 'FAIL'}")
        if churn is not None else "monthly_churn: PASS (not reported)",
        _trend_reason(trend_pass, lm is not None, lm, ttm_avg_net, tol),
    ]

    return {
        "box_type": BOX_TYPE_DIGITAL_MICRO,
        "asking": round(asking, 2),
        "monthly_net_used": round(monthly_net_used, 2),
        "ttm_avg_net": round(ttm_avg_net, 2),
        "last_month_net": round(lm, 2) if lm is not None else None,
        "last_month_revenue": (round(float(last_month_revenue), 2)
                               if last_month_revenue is not None else None),
        "payback_months": round(payback_months, 2) if payback_months is not None else None,
        "net_margin": round(margin, 4) if margin is not None else None,
        "monthly_churn": round(churn, 4) if churn is not None else None,
        "age_months": round(float(age_months), 2) if age_months is not None else None,
        # No debt in a cash-funded acquisition.
        "seller_note_pmt": 0.0,
        "heloc_pmt": 0.0,
        "total_debt": 0.0,
        "free_cash_flow": round(monthly_net_used, 2),
        "dscr": 0.0,
        "price_pass": price_pass,
        "payback_pass": payback_pass,
        "margin_pass": margin_pass,
        "churn_pass": churn_pass,
        "trend_pass": trend_pass,
        "box_pass": box_pass,
        "box_reason": box_reason,
        "flags": flags,
        "config_snapshot": cfg,
    }


def _trend_reason(trend_pass: bool, has_last_month: bool, last_month_net: Optional[float],
                  ttm_avg_net: float, tol: float) -> str:
    if not has_last_month:
        return "trend: FAIL (no last-month figure available)"
    floor = ttm_avg_net * (1 - tol)
    return (
        f"trend last_month ${last_month_net:,.0f} "
        f"{'>=' if trend_pass else '<'} ${floor:,.0f} "
        f"(ttm_avg ${ttm_avg_net:,.0f} - {tol:.0%} tol): "
        f"{'PASS (flat-or-growing)' if trend_pass else 'FAIL (declining)'}"
    )
