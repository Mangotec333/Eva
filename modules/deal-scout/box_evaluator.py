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
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

CONFIG_FILENAME = "deal_box_config.json"
BOXES_DIRNAME = "boxes"

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


def _default_config_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_config(path: Optional[str] = None) -> dict[str, Any]:
    """Return the box config: on-disk file (if present) merged over defaults.

    Nested ``financing`` keys are merged individually so a partial config file
    only needs to override the keys it wants to change.
    """
    cfg: dict[str, Any] = {
        **DEFAULT_CONFIG,
        "financing": dict(DEFAULT_CONFIG["financing"]),
    }
    path = path or _default_config_path()
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        financing = {**cfg["financing"], **(loaded.get("financing") or {})}
        cfg.update({k: v for k, v in loaded.items() if k != "financing"})
        cfg["financing"] = financing
    return cfg


def _boxes_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), BOXES_DIRNAME)


def box_config_path(box_id: str) -> str:
    """Filesystem path to a named box config under the ``boxes/`` directory."""
    return os.path.join(_boxes_dir(), f"{box_id}.json")


def load_box(box_id: str) -> dict[str, Any]:
    """Load a named box config (e.g. ``chad_5mm``) merged over the defaults.

    Named boxes live in ``boxes/<box_id>.json`` and carry the same evaluator
    keys as ``deal_box_config.json`` (min_free_cash_flow_mo, min_dscr,
    trend_decline_tolerance, financing) plus box metadata (id, label,
    owner_email) that ``load_config`` preserves and passes through to the
    ``config_snapshot`` so a verdict stays attributable to its box.
    """
    path = box_config_path(box_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"box config {box_id!r} not found at {path}")
    return load_config(path)


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
) -> dict[str, Any]:
    """Evaluate a deal against the box criteria at the current run-rate.

    Returns a plain dict (JSON-friendly) with the full financing breakdown, the
    three pass/fail sub-checks, the overall ``box_pass`` verdict, a
    ``box_reason`` list, and the ``config_snapshot`` used.
    """
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
