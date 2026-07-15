"""
EVA Treasurer — service layer (track → aggregate → budget → alert → learn)
==========================================================================

Sits between the HTTP/CLI surfaces and the core logic (finance_tracker),
sqlite store, and the Eva State Ledger. The state client is injected (Protocol)
and the Slack alert is a best-effort seam, so the whole service runs offline in
tests with stubs and fires nothing real.

Operations mirror the routes:

  * ``track()``    — log one spend event (idempotent), then check its category
    against the budget cap; on a newly-crossed 80%/100% threshold fire a
    best-effort Slack alert and log a breach event to eva-state.
  * ``summary()``  — spend by category for a period (day/week/month).
  * ``budget()``   — caps vs actual for the period, with usage status.
  * ``set_budget()`` — set/update one category's cap.
  * ``export_csv()`` — CSV dump of all spend events.
  * ``burn()``     — current-month run-rate projection vs total budget.
  * ``daily_summary()`` — log today's spend summary to the backbone (cron).
"""

from __future__ import annotations

import csv
import io
from typing import Optional

import finance_tracker as core
import store
from state_client import StateLedgerClient, build_state_client


class TreasurerService:
    def __init__(self, *, db_path: str = store.DB_PATH,
                 state: Optional[StateLedgerClient] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.state: StateLedgerClient = state or build_state_client(offline=offline)
        store.init_db(self.db_path)

    # -- track one spend -----------------------------------------------------

    def track(self, *, category: str, amount_cents: int, vendor: str = "",
              source_agent: str = "", note: str = "",
              timestamp: Optional[str] = None,
              event_key: Optional[str] = None) -> dict:
        """Log a spend event, then alert if it crosses its budget threshold."""
        cat = core.normalise_category(category)
        try:
            amount = int(amount_cents)
        except (TypeError, ValueError):
            return {"ok": False, "error": "amount_cents must be an integer"}
        if amount < 0:
            return {"ok": False, "error": "amount_cents must be >= 0"}

        budget = store.get_budget(cat, path=self.db_path)
        period = (budget or {}).get("period", "month")
        since = core.period_start_iso(period)

        before = store.category_total(cat, since=since, path=self.db_path)
        event = store.add_event(
            category=cat, amount_cents=amount, vendor=vendor,
            source_agent=source_agent, note=note, timestamp=timestamp,
            event_key=event_key, path=self.db_path)

        # A duplicate (idempotent replay) neither re-counts nor re-alerts.
        if event.get("duplicate"):
            return {"ok": True, "duplicate": True, "event": event,
                    "category": cat, "alert": None}

        after = before + amount
        cap = (budget or {}).get("cap_cents", 0)
        crossed = core.crossed_threshold(before, after, cap)
        usage = core.usage_status(after, cap)

        alert = None
        if crossed:
            msg = core.format_alert(cat, crossed, usage, period)
            slack = core.slack_alert(msg)
            self.state.emit(
                event_type="budget_breach",
                summary=msg,
                entity_id=cat,
                payload={"category": cat, "threshold": crossed,
                         "usage": usage, "period": period,
                         "slack_ok": bool(slack.get("ok"))},
            )
            alert = {"threshold": crossed, "message": msg, "slack": slack}

        self.state.emit(
            event_type="spend_logged",
            summary=f"Treasurer logged ${amount / 100:,.2f} to {cat}"
                    + (f" ({vendor})" if vendor else ""),
            entity_id=cat,
            payload={"category": cat, "amount_cents": amount, "vendor": vendor,
                     "source_agent": source_agent, "period_actual_cents": after},
        )
        return {"ok": True, "duplicate": False, "event": event,
                "category": cat, "usage": usage, "alert": alert}

    # -- reads ---------------------------------------------------------------

    def summary(self, period: str = "month") -> dict:
        """Spend by category for the period (day/week/month)."""
        period = period if period in core.PERIODS else "month"
        since = core.period_start_iso(period)
        by_cat = {c: store.category_total(c, since=since, path=self.db_path)
                  for c in core.CATEGORIES}
        total = sum(by_cat.values())
        return {"period": period, "since": since, "total_cents": total,
                "by_category": by_cat}

    def budget(self, period: Optional[str] = None) -> dict:
        """Caps vs actual for the period, with per-category usage status."""
        budgets = {b["category"]: b for b in store.list_budgets(path=self.db_path)}
        rows = []
        total_cap = total_actual = 0
        for cat in core.CATEGORIES:
            b = budgets.get(cat)
            cap = (b or {}).get("cap_cents", 0)
            per = period or (b or {}).get("period", "month")
            since = core.period_start_iso(per)
            actual = store.category_total(cat, since=since, path=self.db_path)
            usage = core.usage_status(actual, cap)
            usage.update({"category": cat, "period": per})
            rows.append(usage)
            total_cap += cap
            total_actual += actual
        return {"total_cap_cents": total_cap, "total_actual_cents": total_actual,
                "categories": rows}

    def set_budget(self, *, category: str, cap_cents: int,
                   period: str = "month") -> dict:
        cat = core.normalise_category(category)
        per = period if period in core.PERIODS else "month"
        try:
            cap = int(cap_cents)
        except (TypeError, ValueError):
            return {"ok": False, "error": "cap_cents must be an integer"}
        if cap < 0:
            return {"ok": False, "error": "cap_cents must be >= 0"}
        row = store.set_budget(category=cat, cap_cents=cap, period=per,
                               path=self.db_path)
        self.state.emit(
            event_type="budget_set",
            summary=f"Treasurer set {cat} cap to ${cap / 100:,.2f} / {per}",
            entity_id=cat,
            payload={"category": cat, "cap_cents": cap, "period": per})
        return {"ok": True, "budget": row}

    def export_csv(self) -> str:
        """CSV dump of every spend event (header + rows)."""
        events = store.list_events(path=self.db_path)
        buf = io.StringIO()
        cols = ["timestamp", "category", "amount_cents", "vendor",
                "source_agent", "note", "id", "created_at"]
        writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            writer.writerow(e)
        return buf.getvalue()

    def burn(self) -> dict:
        """Current-month run-rate projection vs total monthly budget."""
        since = core.period_start_iso("month")
        actual = sum(store.category_total(c, since=since, path=self.db_path)
                     for c in core.CATEGORIES)
        projection = core.project_month(actual)
        total_cap = sum(b["cap_cents"] for b in store.list_budgets(path=self.db_path))
        projected = projection["projected_month_cents"]
        projection.update({
            "total_monthly_cap_cents": total_cap,
            "projected_vs_cap": core.usage_status(projected, total_cap),
        })
        return projection

    # -- cron: log a daily spend summary to the backbone ---------------------

    def daily_summary(self) -> dict:
        s = self.summary("day")
        res = self.state.emit(
            event_type="spend_daily_summary",
            summary=f"Treasurer daily spend: ${s['total_cents'] / 100:,.2f}",
            entity_id="treasurer",
            payload=s)
        return {"ok": bool(res.get("ok")), "summary": s, "emit": res}


__all__ = ["TreasurerService"]
