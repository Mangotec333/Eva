"""
EVA Treasurer — core spend-tracking + budget logic.

Treasurer tracks all Eva operational spend (API/LLM credits, subscriptions,
marketplace fees, ad spend, deal costs, hosting/domains) against per-category
budget caps, so Vineet always knows the burn rate. Pure stdlib. No bank
integrations — spend is *logged* to Treasurer by the agents that incur it (or
by the CLI/HTTP surfaces).

This module holds the framework-free brain:
  * the fixed category taxonomy + normalisation,
  * period-window math (day / week / month) used by aggregation + burn,
  * budget-usage / threshold-breach classification (80% warn, 100% over),
  * run-rate projection for the current month,
  * a best-effort Slack alert that *reuses* social-publish's slack_client
    (imported, never duplicated) — off by default, honest ``ok=False`` when
    unconfigured so nothing real is ever fired in tests.
"""

from __future__ import annotations

import calendar
import os
from datetime import datetime, timedelta, timezone

# ── Category taxonomy ───────────────────────────────────────────────────────
CAT_LLM_API = "llm_api"            # Anthropic / OpenAI credits
CAT_SUBSCRIPTIONS = "subscriptions"  # GHL / Vercel / Slack / Apollo / etc.
CAT_MARKETPLACE_FEES = "marketplace_fees"  # Empire Flippers / Flippa
CAT_AD_SPEND = "ad_spend"
CAT_DEAL_COSTS = "deal_costs"
CAT_HOSTING_DOMAINS = "hosting_domains"
CAT_OTHER = "other"

CATEGORIES = [
    CAT_LLM_API,
    CAT_SUBSCRIPTIONS,
    CAT_MARKETPLACE_FEES,
    CAT_AD_SPEND,
    CAT_DEAL_COSTS,
    CAT_HOSTING_DOMAINS,
    CAT_OTHER,
]

# Loose aliases so callers/agents can log with natural names.
_ALIASES = {
    "llm": CAT_LLM_API, "api": CAT_LLM_API, "anthropic": CAT_LLM_API,
    "openai": CAT_LLM_API, "claude": CAT_LLM_API, "llm/api": CAT_LLM_API,
    "subscription": CAT_SUBSCRIPTIONS, "saas": CAT_SUBSCRIPTIONS,
    "ghl": CAT_SUBSCRIPTIONS, "vercel": CAT_SUBSCRIPTIONS,
    "slack": CAT_SUBSCRIPTIONS, "apollo": CAT_SUBSCRIPTIONS,
    "marketplace": CAT_MARKETPLACE_FEES, "empire_flippers": CAT_MARKETPLACE_FEES,
    "flippa": CAT_MARKETPLACE_FEES, "broker": CAT_MARKETPLACE_FEES,
    "ads": CAT_AD_SPEND, "ad": CAT_AD_SPEND, "advertising": CAT_AD_SPEND,
    "deal": CAT_DEAL_COSTS, "deals": CAT_DEAL_COSTS, "diligence": CAT_DEAL_COSTS,
    "hosting": CAT_HOSTING_DOMAINS, "domain": CAT_HOSTING_DOMAINS,
    "domains": CAT_HOSTING_DOMAINS, "infra": CAT_HOSTING_DOMAINS,
}

PERIODS = ("day", "week", "month")

# Alert thresholds as a fraction of the cap.
WARN_THRESHOLD = 0.80
OVER_THRESHOLD = 1.00


def normalise_category(raw: str | None) -> str:
    """Map any incoming label to one of the fixed CATEGORIES (default OTHER)."""
    if not raw:
        return CAT_OTHER
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if key in CATEGORIES:
        return key
    return _ALIASES.get(key, CAT_OTHER)


# ── Period window math ──────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def period_start(period: str = "month", now: datetime | None = None) -> datetime:
    """Start (inclusive) of the current day / week (Mon) / month, UTC."""
    now = now or _now()
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    # default month
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def period_start_iso(period: str = "month", now: datetime | None = None) -> str:
    return period_start(period, now).isoformat()


# ── Budget-usage classification ─────────────────────────────────────────────

def usage_status(actual_cents: int, cap_cents: int) -> dict:
    """Classify one category's usage against its cap.

    Returns {actual_cents, cap_cents, pct, status, over_cents} where status is
    'ok' | 'warn' (>=80%) | 'over' (>=100%) | 'uncapped' (no cap set).
    """
    if cap_cents <= 0:
        return {"actual_cents": actual_cents, "cap_cents": cap_cents,
                "pct": None, "status": "uncapped", "over_cents": 0}
    pct = actual_cents / cap_cents
    if pct >= OVER_THRESHOLD:
        status = "over"
    elif pct >= WARN_THRESHOLD:
        status = "warn"
    else:
        status = "ok"
    return {"actual_cents": actual_cents, "cap_cents": cap_cents,
            "pct": round(pct, 4), "status": status,
            "over_cents": max(0, actual_cents - cap_cents)}


def crossed_threshold(before_cents: int, after_cents: int, cap_cents: int) -> str | None:
    """Which threshold (if any) this spend newly *crossed*.

    Returns 'over' if it newly reached/passed 100%, 'warn' if it newly
    reached/passed 80% (but not 100%), else None. Comparing before→after means
    we only alert on the crossing event, not on every spend once over.
    """
    if cap_cents <= 0:
        return None
    before = before_cents / cap_cents
    after = after_cents / cap_cents
    if before < OVER_THRESHOLD <= after:
        return "over"
    if before < WARN_THRESHOLD <= after:
        return "warn"
    return None


# ── Burn / run-rate projection ──────────────────────────────────────────────

def project_month(actual_cents: int, now: datetime | None = None) -> dict:
    """Project month-end spend from month-to-date spend at the current run-rate.

    projected = actual_mtd / days_elapsed * days_in_month
    """
    now = now or _now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day
    daily_rate = actual_cents / day_of_month if day_of_month else 0.0
    projected = int(round(daily_rate * days_in_month))
    return {
        "month_to_date_cents": actual_cents,
        "day_of_month": day_of_month,
        "days_in_month": days_in_month,
        "daily_rate_cents": int(round(daily_rate)),
        "projected_month_cents": projected,
    }


# ── Slack alert — reuse social-publish's client, never duplicate it ─────────

def slack_alert(text: str) -> dict:
    """Best-effort Slack alert via modules/social-publish/slack_client.py.

    Imported lazily from the sibling module so we never duplicate the client.
    Returns honest ``{ok: False, ...}`` when the token/module is missing — no
    network is touched in that case (so tests never fire anything real).
    """
    import sys
    social_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "social-publish")
    if social_dir not in sys.path:
        sys.path.insert(0, social_dir)
    try:
        import slack_client  # type: ignore  # noqa: PLC0415
    except Exception as exc:  # module/dep missing
        return {"ok": False, "error": f"slack_client unavailable: {exc}"}
    if not slack_client.is_configured():
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    return slack_client.post_message(text)


def format_alert(category: str, status: str, usage: dict, period: str) -> str:
    """Human-readable budget-breach line for Slack."""
    pct = usage.get("pct")
    pct_str = f"{pct * 100:.0f}%" if pct is not None else "n/a"
    actual = usage["actual_cents"] / 100
    cap = usage["cap_cents"] / 100
    flag = "🚨 OVER BUDGET" if status == "over" else "⚠️ budget warning"
    return (f"{flag} — Treasurer: `{category}` at {pct_str} of its {period} cap "
            f"(${actual:,.2f} / ${cap:,.2f}).")


__all__ = [
    "CATEGORIES", "PERIODS",
    "CAT_LLM_API", "CAT_SUBSCRIPTIONS", "CAT_MARKETPLACE_FEES", "CAT_AD_SPEND",
    "CAT_DEAL_COSTS", "CAT_HOSTING_DOMAINS", "CAT_OTHER",
    "WARN_THRESHOLD", "OVER_THRESHOLD",
    "normalise_category", "period_start", "period_start_iso",
    "usage_status", "crossed_threshold", "project_month",
    "slack_alert", "format_alert",
]
