"""
EVA Treasurer — budgeting / rollup engine.

Computes spend-vs-income rollups over daily, weekly, and monthly windows for a
single side. Because a ``TreasurerStore`` is bound to one side, every rollup is
inherently scoped to that side — personal and business totals are computed from
different database files and never commingled.

Sign convention (see ``models.py``): negative cents = spend, positive = income.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

PERIODS = ("day", "week", "month")


def period_bounds(period: str, ref: Optional[date] = None) -> tuple[date, date]:
    """Return (start, end) inclusive dates for the window containing ``ref``."""
    ref = ref or date.today()
    if period == "day":
        return ref, ref
    if period == "week":  # Monday-anchored week
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = ref.replace(day=1)
        if start.month == 12:
            nxt = start.replace(year=start.year + 1, month=1)
        else:
            nxt = start.replace(month=start.month + 1)
        return start, nxt - timedelta(days=1)
    raise ValueError(f"invalid period {period!r}; must be one of {PERIODS}")


def rollup(store, period: str = "month", ref: Optional[date] = None) -> dict:
    """Spend/income rollup for one window on one side.

    Returns income, spend, net (all cents), plus per-category spend and the
    window bounds. ``side`` is echoed so the caller can label the result.
    """
    start, end = period_bounds(period, ref)
    txns = store.list_transactions(start=start.isoformat(), end=end.isoformat())

    income = sum(t["amount_cents"] for t in txns if t["amount_cents"] > 0)
    spend = sum(-t["amount_cents"] for t in txns if t["amount_cents"] < 0)

    by_category: dict[str, int] = {}
    for t in txns:
        if t["amount_cents"] < 0:
            cat = t["category"] or "uncategorized"
            by_category[cat] = by_category.get(cat, 0) + (-t["amount_cents"])

    return {
        "side": store.side,
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income_cents": income,
        "spend_cents": spend,
        "net_cents": income - spend,
        "transaction_count": len(txns),
        "spend_by_category": dict(sorted(by_category.items(),
                                         key=lambda kv: kv[1], reverse=True)),
    }


def all_rollups(store, ref: Optional[date] = None) -> dict:
    """Return daily, weekly, and monthly rollups for one side."""
    return {
        "side": store.side,
        "day": rollup(store, "day", ref),
        "week": rollup(store, "week", ref),
        "month": rollup(store, "month", ref),
    }
