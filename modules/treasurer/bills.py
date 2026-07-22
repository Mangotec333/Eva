"""
EVA Treasurer — bill due-date tracking + credit utilization monitoring.

Two responsibilities, both scoped to one side (the store is single-side):

  1. Upcoming bills: bills due within a horizon (default 30 days), sorted by due
     date, with an ``overdue`` flag and days-until.
  2. Credit utilization: for every credit account, utilization = balance /
     credit_limit. Anything at/above the configurable threshold (default 0.30 →
     30%) is flagged as an alert. High utilization is the single biggest
     controllable factor in a credit score, so this is the credit-score
     protection feature.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from models import DEFAULT_UTILIZATION_THRESHOLD


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)


def upcoming_bills(store, within_days: int = 30, ref: Optional[date] = None) -> list[dict]:
    """Unpaid bills due within ``within_days`` (plus any overdue), sorted by date."""
    ref = ref or date.today()
    out = []
    for bill in store.list_bills(include_paid=False):
        try:
            due = _parse_date(bill["due_date"])
        except ValueError:
            continue
        days_until = (due - ref).days
        if days_until > within_days:
            continue
        out.append({
            **bill,
            "side": store.side,
            "days_until_due": days_until,
            "overdue": days_until < 0,
        })
    out.sort(key=lambda b: b["due_date"])
    return out


def utilization_report(store,
                       threshold: float = DEFAULT_UTILIZATION_THRESHOLD) -> dict:
    """Per-card utilization ratios and threshold alerts for one side.

    Returns overall utilization across all credit lines plus a per-card list;
    each card is flagged when its ratio >= ``threshold``.
    """
    cards = store.credit_accounts()
    per_card = []
    total_balance = 0
    total_limit = 0
    alerts = []

    for card in cards:
        limit = card["credit_limit_cents"]
        balance = card["balance_cents"]
        total_balance += balance
        total_limit += limit
        ratio = (balance / limit) if limit > 0 else 0.0
        flagged = limit > 0 and ratio >= threshold
        entry = {
            "account_id": card["id"],
            "side": store.side,
            "institution": card["institution"],
            "name": card["name"],
            "balance_cents": balance,
            "credit_limit_cents": limit,
            "utilization": round(ratio, 4),
            "utilization_pct": round(ratio * 100, 2),
            "threshold": threshold,
            "alert": flagged,
        }
        per_card.append(entry)
        if flagged:
            alerts.append(entry)

    overall = (total_balance / total_limit) if total_limit > 0 else 0.0
    per_card.sort(key=lambda c: c["utilization"], reverse=True)
    alerts.sort(key=lambda c: c["utilization"], reverse=True)

    return {
        "side": store.side,
        "threshold": threshold,
        "overall_utilization": round(overall, 4),
        "overall_utilization_pct": round(overall * 100, 2),
        "total_balance_cents": total_balance,
        "total_limit_cents": total_limit,
        "cards": per_card,
        "alerts": alerts,
        "alert_count": len(alerts),
    }
